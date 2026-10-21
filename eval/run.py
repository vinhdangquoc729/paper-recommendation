"""Chạy một cấu hình trên tập tác giả: loại bài đã biết, xếp hạng toàn bộ pool (không lấy mẫu), tính độ đo."""
import logging

import numpy as np
import pandas as pd

from eval import metrics
from eval.protocol import Case, World

log = logging.getLogger(__name__)

KS = (10, 20)
K_BEYOND = 10            # độ đo ngoài độ chính xác tính trên top-10, cỡ một trang gợi ý
NEW_DAYS = 30
STRONG = 2               # mức ground truth được coi là "trích mạnh"


def evaluate(world: World, cases: list[Case], method, q: np.ndarray | None = None,
             batch: int = 256) -> tuple[pd.DataFrame, list[np.ndarray]]:
    """-> (độ đo theo từng tác giả, top-k theo chỉ số bài). q: điểm chất lượng tại T theo chỉ số bài."""
    k_max = max(KS)
    t = np.datetime64(world.T)
    rows, tops = [], []
    for s in range(0, len(cases), batch):
        part = cases[s:s + batch]
        sc = method.scores(world, part).astype(np.float32, copy=False)
        for row, case in zip(sc, part):
            known = world.pool_pos[case.known()]
            row[known[known >= 0]] = -np.inf

            k = min(k_max, len(row))
            top_pos = np.argpartition(-row, k - 1)[:k]
            top_pos = top_pos[np.argsort(-row[top_pos], kind="stable")]
            top = world.pool[top_pos[np.isfinite(row[top_pos])]]
            gt_pos = world.pool_pos[case.gt]
            hits = np.isin(top, case.gt)
            gt_best = row[gt_pos].max()   # -inf: mọi bài đúng nằm ngoài tập ứng viên của cấu hình

            r = {"author": case.author, "n_gt": len(case.gt), "n_profile": len(case.authored) + len(case.prior)}
            for k in KS:
                r[f"recall@{k}"] = metrics.recall_at_k(hits, len(case.gt), k)
                r[f"ndcg@{k}"] = metrics.ndcg_at_k(hits, len(case.gt), k)
            r["mrr"] = metrics.reciprocal_rank(int((row > gt_best).sum()) + 1) if np.isfinite(gt_best) else 0.0
            if case.grade is not None:
                g = dict(zip(case.gt.tolist(), case.grade.tolist()))
                top_g = np.array([g.get(int(i), 0) for i in top])
                for k in KS:
                    r[f"ndcg@{k}g"] = metrics.ndcg_graded(top_g, case.grade, k)
                n_strong = int((case.grade >= STRONG).sum())
                r[f"recall@{k_max}s"] = (top_g[:k_max] >= STRONG).sum() / n_strong if n_strong else np.nan
            head = top[:K_BEYOND]
            age = (t - world.first_seen[head]) / np.timedelta64(1, "D")
            r["age_days"] = float(age.mean())
            r["new@30d"] = float((age < NEW_DAYS).mean())
            if q is not None:
                r["q"] = float(np.nanmean(q[head]))
            if world.emb is not None:
                r["ild"] = metrics.intra_list_distance(np.asarray(world.emb[head], dtype=np.float32))
            rows.append(r)
            tops.append(top)
        log.debug("[eval] %s: %d/%d", method.name, s + len(part), len(cases))
    return pd.DataFrame(rows), tops


def coverage(world: World, tops: list[np.ndarray], k: int = K_BEYOND) -> float:
    """Tỉ lệ pool xuất hiện trong ít nhất một danh sách top-k."""
    return len(np.unique(np.concatenate([t[:k] for t in tops]))) / len(world.pool)


ACCURACY = [f"{m}@{k}" for k in KS for m in ("recall", "ndcg")] + ["mrr"]
GRADED = [f"ndcg@{k}g" for k in KS] + [f"recall@{max(KS)}s"]
BEYOND = ["age_days", "new@30d", "q", "ild"]


def summarize(results: dict[str, pd.DataFrame], cov: dict[str, float]) -> pd.DataFrame:
    """Bảng trung bình theo cấu hình; độ đo chính kèm khoảng tin cậy 95% (bootstrap theo tác giả)."""
    out = []
    for name, df in results.items():
        r = {"method": name}
        for m in ACCURACY + GRADED:
            if m in df:
                r[m] = round(df[m].mean(), 4)
        lo, hi = metrics.bootstrap_ci(df["ndcg@10"].to_numpy())
        r["ndcg@10 CI95"] = f"[{lo:.4f}, {hi:.4f}]"
        for m in BEYOND:
            if m in df:
                r[m] = round(df[m].mean(), 3)
        r["coverage"] = round(cov[name], 4)
        out.append(r)
    return pd.DataFrame(out)


def compare(results: dict[str, pd.DataFrame], ref: str, metric: str = "ndcg@10") -> pd.DataFrame:
    """Mỗi cấu hình so với `ref` trên cùng tập tác giả (kiểm định cặp)."""
    a = results[ref][metric].to_numpy()
    rows = [{"method": n, "vs": ref, "metric": metric, **metrics.paired_diff(a, df[metric].to_numpy())}
            for n, df in results.items() if n != ref]
    return pd.DataFrame(rows)
