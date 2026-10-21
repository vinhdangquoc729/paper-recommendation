"""Baseline của spec mục 12.3. Mỗi cấu hình trả điểm của mọi bài trong pool cho một lô tác giả;
việc loại bài đã viết / đã trích và chấm điểm do eval.run làm, giống nhau cho mọi cấu hình.

- B0 Random.
- B1 Popularity: số bài công khai trước T trích bài đó (trong corpus).
- B2 Content: hồ sơ là một vector, trung bình có trọng số embedding các bài trong hồ sơ (spec 7.2):
  bài đã viết 1,0 (x1,2 nếu đứng đầu), bài đã trích 0,5 (chưa lọc reference), nhân time decay exp(-Δt / 3 năm).
- B3 Content đa sở thích: cùng tập bài và trọng số, phân cụm thành tối đa 5 sở thích (recsys.profile),
  điểm = max_c π'_c · cos(u_c, e_p).
"""
import numpy as np

from eval.protocol import Case, World
from recsys import profile
from recsys.profile import TAU_YEARS, W_AUTHORED, W_CITED, W_FIRST_AUTHOR


class Random:
    name = "B0 random"

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def scores(self, world: World, cases: list[Case]) -> np.ndarray:
        return self.rng.random((len(cases), len(world.pool)), dtype=np.float32)


class Popularity:
    name = "B1 popularity"

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def scores(self, world: World, cases: list[Case]) -> np.ndarray:
        pop = world.in_degree[world.pool].astype(np.float32)
        # rất nhiều bài cùng 0 lượt trích: phá hoà ngẫu nhiên thay vì theo thứ tự trong bảng
        return pop + 0.5 * self.rng.random((len(cases), len(pop)), dtype=np.float32)


def profile_weights(world: World, case: Case) -> tuple[np.ndarray, np.ndarray]:
    """-> (chỉ số bài, trọng số) của hồ sơ tại T; bài vừa viết vừa trích lấy trọng số lớn nhất."""
    t = np.datetime64(world.T)
    w: dict[int, float] = {}

    def decay(d) -> float:
        return float(np.exp(-((t - d) / np.timedelta64(1, "D")) / 365.25 / TAU_YEARS))

    for i, first in zip(case.authored, case.first_author):
        w[int(i)] = W_AUTHORED * (W_FIRST_AUTHOR if first else 1.0) * decay(world.first_seen[i])
    for r, d in case.prior.items():
        w[r] = max(w.get(r, 0.0), W_CITED * decay(d))
    idx = np.fromiter(w.keys(), dtype=int)
    return idx, np.fromiter(w.values(), dtype=float)


class ContentMean:
    name = "B2 content"

    def __init__(self, world: World):
        if world.emb is None:
            raise ValueError("cần embedding")
        self.pool_emb = np.ascontiguousarray(world.emb[world.pool], dtype=np.float32)

    def scores(self, world: World, cases: list[Case]) -> np.ndarray:
        prof = np.zeros((len(cases), self.pool_emb.shape[1]), dtype=np.float32)
        for k, case in enumerate(cases):
            idx, w = profile_weights(world, case)
            prof[k] = profile.mean_profile(world.emb[idx], w)
        return prof @ self.pool_emb.T


class ContentMulti(ContentMean):
    name = "B3 content multi"

    def __init__(self, world: World, k_max: int = profile.K_MAX, floor: float = profile.PI_FLOOR):
        super().__init__(world)
        self.k_max, self.floor = k_max, floor

    def scores(self, world: World, cases: list[Case]) -> np.ndarray:
        out = np.empty((len(cases), len(self.pool_emb)), dtype=np.float32)
        for k, case in enumerate(cases):
            idx, w = profile_weights(world, case)
            vecs = np.asarray(world.emb[idx], dtype=np.float32)
            cent, pi = profile.cluster_profile(vecs, w, profile.n_clusters(len(idx), self.k_max))
            out[k] = profile.multi_interest_scores(self.pool_emb, cent, pi, self.floor)
        return out
