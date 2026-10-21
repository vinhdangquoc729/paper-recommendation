"""Sinh ứng viên và đặc trưng (spec mục 8, 9.1) cho người dùng tại T. Dùng chung cho sản phẩm và đánh giá.

Ứng viên của mỗi người dùng (khoảng 500-1000 bài) là hợp của top bài theo từng nguồn: nội dung, độ phổ biến,
co-citation, coupling, bài trích người dùng, bài của đồng tác giả. Bài đã biết (Case.known) bị loại.

Đồ thị trích dẫn chỉ gồm cạnh từ bài công khai trước T. Mỗi chế độ trọng số cạnh (features.reference_filter.MODES)
cho một bộ đặc trưng riêng: rel_{mode} (hồ sơ đa sở thích, bài đã trích có trọng số 0,5·w), cocit_{mode},
coupling_{mode}. Đánh giá tính đủ 5 chế độ để so sánh; sản phẩm chỉ cần những chế độ mô hình dùng.
"""
import logging
import time
from dataclasses import dataclass

import numpy as np

from features import reference_filter
from recsys import profile
from recsys.graph import GraphScorer, citation_matrix
from recsys.snapshot import Case, World

log = logging.getLogger(__name__)

MODES = reference_filter.MODES


def feature_names(modes) -> list[str]:
    return (["rel_mean"] + [f"rel_{m}" for m in modes] + ["pop", "q", "age"]
            + [f"cocit_{m}" for m in modes] + [f"coupling_{m}" for m in modes] + ["cites_me", "coauthor"])


FEATURES = feature_names(MODES)
# số ứng viên lấy từ mỗi nguồn (nguồn nào không có trong bộ đặc trưng thì bỏ qua)
SOURCES = {"rel_raw": 200, "rel_mean": 100, "pop": 100, "cocit_raw": 100, "cocit_w": 100,
           "coupling_raw": 100, "coupling_w": 100, "cites_me": 100, "coauthor": 100}
M_MAX = sum(SOURCES.values())
# Nguồn "pref" (chỉ sản phẩm): bài khớp lĩnh vực / từ khoá khai báo (Case.boost), xếp theo độ giống nội dung
PREF_TOP = 100


@dataclass
class Cache:
    """Ứng viên và đặc trưng thô của một tập người dùng. Ô không có ứng viên: cand = -1."""
    authors: list[str]
    cand: np.ndarray      # (B, M) vị trí trong pool
    F: np.ndarray         # (B, M, số đặc trưng) float32
    y: np.ndarray         # (B, M) bool, ứng viên thuộc ground truth
    n_gt: np.ndarray      # (B,) kích thước ground truth (kể cả phần không lọt vào ứng viên)

    @property
    def valid(self) -> np.ndarray:
        return self.cand >= 0

    def save(self, path) -> None:
        np.savez(path, authors=np.array(self.authors), cand=self.cand, F=self.F, y=self.y, n_gt=self.n_gt)

    @classmethod
    def load(cls, path) -> "Cache":
        z = np.load(path)
        return cls(list(z["authors"]), z["cand"], z["F"], z["y"], z["n_gt"])


def _decay(t: np.datetime64, dates) -> np.ndarray:
    days = (t - np.asarray(dates, dtype="datetime64[D]")) / np.timedelta64(1, "D")
    return np.exp(-np.maximum(days, 0) / 365.25 / profile.TAU_YEARS)


class FeatureBuilder:
    def __init__(self, world: World, q: np.ndarray, modes=MODES):
        if "raw" not in modes:
            modes = ("raw", *modes)   # rel_mean, cites_me và nguồn ứng viên chính dùng đồ thị chưa lọc
        self.w, self.modes = world, tuple(modes)
        self.features = feature_names(self.modes)
        t = self.t = np.datetime64(world.T)
        n = len(world.item_ids)
        emb = world.emb
        self.pool_emb = np.ascontiguousarray(emb[world.pool], dtype=np.float32)

        e = world.edges[world.first_seen[world.edges.a.to_numpy()] < t].reset_index(drop=True)
        a, b = e.a.to_numpy(), e.b.to_numpy()
        sim = np.concatenate([(np.asarray(emb[a[s:s + 50_000]]) * np.asarray(emb[b[s:s + 50_000]])).sum(axis=1)
                              for s in range(0, len(e), 50_000)] or [np.zeros(0)])
        n_citing = max(len(np.unique(a)), 2)
        self.edge_w = {m: reference_filter.edge_weights(e, sim, world.in_degree, n_citing, m) for m in self.modes}
        self.A = {m: citation_matrix(a, b, w, n) for m, w in self.edge_w.items()}
        self.graph = {m: GraphScorer(A) for m, A in self.A.items()}
        if "w" in self.edge_w:
            log.info("[pipeline] %d cạnh trước T từ %d bài; w: trung vị %.2f, %.0f%% cạnh có w < θ=%.1f", len(e),
                     n_citing, np.median(self.edge_w["w"]) if len(e) else 0,
                     100 * (self.edge_w["w"] < reference_filter.THETA_EDGE).mean() if len(e) else 0,
                     reference_filter.THETA_EDGE)

        pool = world.pool
        self.pop = np.log1p(world.in_degree[pool]).astype(np.float32)
        qp = q[pool]
        self.q = np.where(np.isnan(qp), np.nanmean(qp), qp).astype(np.float32)
        self.age = np.log1p((t - world.first_seen[pool]) / np.timedelta64(1, "D")).astype(np.float32)
        self.author_pool: dict[str, list[int]] = {}
        for pos, i in enumerate(pool):
            for au in world.item_authors[i]:
                self.author_pool.setdefault(au, []).append(pos)

    def profile(self, case: Case, mode: str) -> tuple[np.ndarray, np.ndarray]:
        """Hồ sơ (spec 7.2): bài đã viết 1,0 (đứng đầu x1,2); bài đã trích 0,5 · w(bài của mình, bài được trích);
        bài trong `extra` (đã lưu, đã đọc) theo trọng số đã cho; tất cả nhân time decay. Bài trùng: lấy max."""
        w: dict[int, float] = {}
        dec = _decay(self.t, self.w.first_seen[case.authored])
        for i, first, d in zip(case.authored, case.first_author, dec):
            w[int(i)] = profile.W_AUTHORED * (profile.W_FIRST_AUTHOR if first else 1.0) * d
        if case.prior:
            r = np.fromiter(case.prior.keys(), dtype=int)
            ew = self.A[mode][case.authored][:, r].max(axis=0).toarray().ravel()
            cited = profile.W_CITED * _decay(self.t, list(case.prior.values())) * ew
            for j, v in zip(r, cited):
                if v > 0:
                    w[int(j)] = max(w.get(int(j), 0.0), float(v))
        for j, v in case.extra.items():
            w[int(j)] = max(w.get(int(j), 0.0), float(v))
        return np.fromiter(w.keys(), dtype=int), np.fromiter(w.values(), dtype=float)

    def build(self, cases: list[Case], batch: int = 32, sources: dict[str, int] | None = None) -> Cache:
        sources = {s: k for s, k in (sources or SOURCES).items() if s in self.features}
        B, P, d = len(cases), len(self.w.pool), len(self.features)
        m_max = sum(sources.values()) + (PREF_TOP if any(c.boost is not None for c in cases) else 0)
        cand = np.full((B, m_max), -1, dtype=np.int32)
        F = np.zeros((B, m_max, d), dtype=np.float32)
        y = np.zeros((B, m_max), dtype=bool)
        col = {f: j for j, f in enumerate(self.features)}
        n = len(self.w.item_ids)
        start = time.monotonic()
        for s in range(0, B, batch):
            part = cases[s:s + batch]
            full = np.zeros((len(part), P, d), dtype=np.float32)
            X = {m: np.zeros((n, len(part)), dtype=np.float32) for m in self.modes}
            X_auth = np.zeros((n, len(part)), dtype=np.float32)
            for k, case in enumerate(part):
                X_auth[case.authored, k] = 1
                for m in self.modes:
                    idx, w = self.profile(case, m)
                    if len(idx) == 0:
                        continue
                    X[m][idx, k] = w
                    vecs = np.asarray(self.w.emb[idx], dtype=np.float32)
                    if m == "raw":
                        full[k, :, col["rel_mean"]] = self.pool_emb @ profile.mean_profile(vecs, w)
                    cent, pi = profile.cluster_profile(vecs, w)
                    full[k, :, col[f"rel_{m}"]] = profile.multi_interest_scores(self.pool_emb, cent, pi)
                coa = {au for i in case.authored for au in self.w.item_authors[i]} - {case.author}
                for au in coa:
                    np.add.at(full[k, :, col["coauthor"]], self.author_pool.get(au, []), 1)
            for m in self.modes:
                full[:, :, col[f"cocit_{m}"]] = self.graph[m].cocitation(X[m])[self.w.pool].T
                full[:, :, col[f"coupling_{m}"]] = self.graph[m].coupling(X[m])[self.w.pool].T
            full[:, :, col["cites_me"]] = (self.A["raw"] @ X_auth)[self.w.pool].T
            full[:, :, col["pop"]], full[:, :, col["q"]], full[:, :, col["age"]] = self.pop, self.q, self.age

            for k, case in enumerate(part):
                known = self.w.pool_pos[case.known()]
                blocked = np.zeros(P, dtype=bool)
                blocked[known[known >= 0]] = True
                if case.allowed is not None:
                    blocked |= ~case.allowed[self.w.pool]
                srcs = list(sources.items()) + ([("pref", PREF_TOP)] if case.boost is not None else [])
                picked = []
                for src, top in srcs:
                    if src == "pref":
                        x = np.where(case.boost[self.w.pool], full[k, :, col["rel_raw"]], -np.inf)
                    else:
                        x = full[k, :, col[src]].copy()
                    x[blocked] = -np.inf
                    if src in ("cites_me", "coauthor"):
                        x[x <= 0] = -np.inf
                    if src == "coauthor":   # nhiều bài của đồng tác giả: ưu tiên bài gần nội dung
                        x = np.where(np.isfinite(x), full[k, :, col["rel_raw"]], -np.inf)
                    top_pos = np.argpartition(-x, min(top, P - 1))[:top]
                    picked.append(top_pos[np.isfinite(x[top_pos])])
                c = np.unique(np.concatenate(picked))
                cand[s + k, :len(c)] = c
                F[s + k, :len(c)] = full[k, c]
                y[s + k, :len(c)] = np.isin(c, self.w.pool_pos[case.gt])
            if B > batch:
                log.info("[pipeline] đặc trưng %d/%d người dùng (%.0fs)", s + len(part), B, time.monotonic() - start)
        n_gt = np.array([len(c.gt) for c in cases])
        if n_gt.sum():
            log.info("[pipeline] trung bình %.0f ứng viên / người, phủ %.1f%% ground truth",
                     (cand >= 0).sum(1).mean(), 100 * (y.sum(1) / np.maximum(n_gt, 1)).mean())
        return Cache([c.author for c in cases], cand, F, y, n_gt)
