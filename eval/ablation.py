"""Thử nghiệm từng thành phần (spec 12.3): B4-B8 và ablation, trên cùng tập ứng viên (eval.hybrid).

- Hàm tuyến tính: trọng số học trên tập train bằng coordinate ascent tối đa ndcg@10 (đặc trưng nội dung đầu tiên giữ
  nguyên trọng số làm mốc), rồi chấm trên val. Mỗi cấu hình học trọng số riêng, khởi đầu từ cấu hình đã học có nhiều
  đặc trưng chung nhất (tránh kẹt ở điểm kém hơn chính cấu hình con của nó).
- B7: MMR trên điểm của B6 với nhiều λ.
- B8: LightGBM LambdaRank trên mọi đặc trưng, dừng sớm theo 20% tác giả train giữ lại.

Mục tiêu học (`objective`): `binary` (mọi bài ground truth như nhau) hoặc `graded` (mức 0-3 của eval.protocol,
gain 2^mức − 1, bài trích cho có = 0). Báo cáo luôn có cả độ đo nhị phân lẫn nhiều mức.
"""
from dataclasses import dataclass

import logging
import time

import numpy as np
import pandas as pd

from eval import run
from eval.hybrid import FEATURES, MODES, Cache, CachedScores
from eval.protocol import Case, World
from recsys.ranking import linear_scores, standardize
from recsys.rerank import mmr

log = logging.getLogger(__name__)

GRID = (-2.0, -1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0)
N_PASSES = 5
MMR_POOL = 100
MMR_LAMBDAS = (0.9, 0.7, 0.5)


DISC = 1 / np.log2(np.arange(2, 12))


@dataclass
class Target:
    """Nhãn của ứng viên theo mục tiêu học: labels (B, M) int, gain (B, M), idcg@10 (B,) tính trên MỌI ground truth."""
    labels: np.ndarray
    gain: np.ndarray
    idcg: np.ndarray


def make_target(cache: Cache, cases: list[Case], world: World, objective: str) -> Target:
    if objective == "binary":
        labels = cache.y.astype(np.int8)
        idcg = np.cumsum(DISC)[np.minimum(cache.n_gt, 10) - 1]
    elif objective == "graded":
        labels = np.zeros(cache.cand.shape, dtype=np.int8)
        idcg = np.zeros(len(cases))
        for i, case in enumerate(cases):
            g = dict(zip(world.pool_pos[case.gt].tolist(), case.grade.tolist()))
            labels[i] = [g.get(int(c), 0) for c in cache.cand[i]]
            ideal = 2.0 ** np.sort(case.grade)[::-1][:10] - 1
            idcg[i] = (ideal * DISC[:len(ideal)]).sum()
    else:
        raise ValueError(objective)
    return Target(labels, (2.0 ** labels - 1).astype(np.float32), idcg)


def ndcg10(S: np.ndarray, tgt: Target) -> float:
    """Trung bình ndcg@10 trên các tác giả có idcg > 0."""
    top = np.argpartition(-S, 10, axis=1)[:, :10]
    top = np.take_along_axis(top, np.argsort(-np.take_along_axis(S, top, 1), axis=1), 1)
    gain = np.take_along_axis(tgt.gain, top, 1) * np.isfinite(np.take_along_axis(S, top, 1))
    ok = tgt.idcg > 0
    return float(((gain * DISC).sum(1)[ok] / tgt.idcg[ok]).mean())


def tune(Z: np.ndarray, cache: Cache, tgt: Target, feats: list[str],
         init: dict[str, float] | None = None) -> tuple[np.ndarray, float]:
    """Coordinate ascent trên lưới GRID -> (trọng số, ndcg@10 trên train). Đặc trưng đầu tiên giữ nguyên trọng số."""
    cols = [FEATURES.index(f) for f in feats]
    Zc = np.ascontiguousarray(Z[..., cols])
    w = np.array([(init or {}).get(f, 0.0) for f in feats])
    if w[0] == 0:
        w[0] = 1.0
    best = ndcg10(linear_scores(Zc, w, cache.valid), tgt)
    for _ in range(N_PASSES):
        improved = False
        for j in range(1, len(feats)):
            for g in GRID:
                if g == w[j]:
                    continue
                w2 = w.copy()
                w2[j] = g
                sc = ndcg10(linear_scores(Zc, w2, cache.valid), tgt)
                if sc > best + 1e-5:
                    best, w, improved = sc, w2, True
        if not improved:
            break
    return w, best


def linear_configs() -> dict[str, list[str]]:
    """Tên cấu hình -> đặc trưng (đặc trưng đầu tiên là nội dung, trọng số cố định 1)."""
    def chain(m):
        return [f"rel_{m}", f"cocit_{m}", f"coupling_{m}"]

    full = [*chain("w"), "rel_mean", "pop", "cites_me", "coauthor", "q", "age"]
    cfg = {
        "C0 nội dung (B3 trên ứng viên)": ["rel_raw"],
        "B4 + đồ thị chưa lọc": chain("raw"),
        **{f"B5 + đồ thị lọc [{m}]": chain(m) for m in MODES if m != "raw"},
        "B5 + độ phổ biến": [*chain("w"), "pop"],
        "B5 + độ phổ biến + danh tính": [*chain("w"), "pop", "cites_me", "coauthor"],
        "B6 đủ (+ q, tuổi, rel_mean)": full,
        "B6 nhưng đồ thị chưa lọc": [*chain("raw"), "rel_mean", "pop", "cites_me", "coauthor", "q", "age"],
    }
    groups = {"nội dung đa sở thích": ["rel_w"], "co-citation": ["cocit_w"], "coupling": ["coupling_w"],
              "rel_mean": ["rel_mean"], "độ phổ biến": ["pop"], "danh tính": ["cites_me", "coauthor"],
              "q": ["q"], "tuổi": ["age"]}
    for g, drop in groups.items():
        feats = [f for f in full if f not in drop]
        if g == "nội dung đa sở thích":
            feats = ["rel_mean"] + [f for f in feats if f != "rel_mean"]   # vẫn cần một đặc trưng nội dung làm mốc
        cfg[f"B6 bỏ {g}"] = feats
    return cfg


def mmr_scores(S: np.ndarray, cache: Cache, pool_emb: np.ndarray, lam: float, k: int = 20) -> np.ndarray:
    """Đưa k bài MMR chọn lên đầu (theo thứ tự chọn), phần còn lại giữ thứ tự cũ."""
    out = S.copy()
    for i in range(len(S)):
        top = np.argsort(-S[i])[:MMR_POOL]
        top = top[np.isfinite(S[i][top])]
        if len(top) == 0:
            continue
        chosen = top[mmr(S[i][top], pool_emb[cache.cand[i][top]], k, lam)]
        out[i][chosen] = S[i].max() + 1 + np.arange(len(chosen))[::-1]
    return out


def lightgbm_scores(Z_tr: np.ndarray, tr: Cache, tgt: Target, Z_va: np.ndarray, va: Cache,
                    seed: int = 0) -> tuple[np.ndarray, dict]:
    import lightgbm as lgb

    rng = np.random.default_rng(seed)
    has_pos = (tgt.labels > 0).any(axis=1)
    rows = np.flatnonzero(has_pos)
    hold = rng.random(len(rows)) < 0.2

    def pack(idx):
        v = tr.valid[idx]
        return Z_tr[idx][v], tgt.labels[idx][v].astype(int), v.sum(axis=1)

    X1, y1, g1 = pack(rows[~hold])
    X2, y2, g2 = pack(rows[hold])
    model = lgb.LGBMRanker(objective="lambdarank", n_estimators=600, learning_rate=0.05, num_leaves=31,
                           min_child_samples=100, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                           random_state=seed, verbose=-1)
    model.fit(X1, y1, group=g1, eval_set=[(X2, y2)], eval_group=[g2], eval_at=[10],
              callbacks=[lgb.early_stopping(40, verbose=False)])
    S = np.full(va.cand.shape, -np.inf, dtype=np.float32)
    S[va.valid] = model.predict(Z_va[va.valid])
    importance = dict(zip(FEATURES, model.booster_.feature_importance("gain")))
    return S, {"best_iteration": model.best_iteration_, "importance": importance}


def run_ablation(world, q, train: Cache, train_cases, val: Cache, val_cases, baselines_results: dict,
                 objective: str = "binary") -> tuple[dict, dict, pd.DataFrame, dict]:
    """-> (kết quả từng tác giả theo cấu hình, coverage, bảng trọng số đã học, {cấu hình: (trọng số, ndcg train)})."""
    tgt = make_target(train, train_cases, world, objective)
    Z_tr = standardize(train.F, train.valid, FEATURES)
    Z_va = standardize(val.F, val.valid, FEATURES)
    pool_emb = np.asarray(world.emb[world.pool], dtype=np.float32)
    results, cov = dict(baselines_results["results"]), dict(baselines_results["coverage"])
    weights = []

    def add(name, S):
        method = CachedScores(name, val, S)
        df, tops = run.evaluate(world, val_cases, method, q)
        results[name], cov[name] = df, run.coverage(world, tops)
        log.info("[ablation] %-40s ndcg@10 %.4f  ndcg@10g %.4f  recall@20s %.4f", name, df["ndcg@10"].mean(),
                 df["ndcg@10g"].mean(), df["recall@20s"].mean())

    scores, learned = {}, {}
    for name, feats in linear_configs().items():
        start = time.monotonic()
        init = max(learned.values(), key=lambda lw: (len(set(lw[0]) & set(feats)), lw[1]), default=({}, 0))[0]
        w, train_ndcg = tune(Z_tr, train, tgt, feats, init)
        learned[name] = (dict(zip(feats, w)), train_ndcg)
        weights.append({"config": name, "ndcg@10 train": round(train_ndcg, 4), **dict(zip(feats, np.round(w, 2)))})
        cols = [FEATURES.index(f) for f in feats]
        scores[name] = linear_scores(np.ascontiguousarray(Z_va[..., cols]), w, val.valid)
        log.info("[ablation] học trọng số %s: %s (%.0fs)", name, dict(zip(feats, np.round(w, 2))),
                 time.monotonic() - start)
        add(name, scores[name])

    b6 = scores["B6 đủ (+ q, tuổi, rel_mean)"]
    for lam in MMR_LAMBDAS:
        add(f"B7 = B6 + MMR λ={lam}", mmr_scores(b6, val, pool_emb, lam))

    S8, info = lightgbm_scores(Z_tr, train, tgt, Z_va, val)
    log.info("[ablation] LightGBM: %d cây", info["best_iteration"])
    add("B8 LightGBM LambdaRank", S8)
    imp = pd.Series(info["importance"])
    weights.append({"config": "B8 LightGBM (gain, %)", **(100 * imp / imp.sum()).round(1).to_dict()})
    return results, cov, pd.DataFrame(weights), learned
