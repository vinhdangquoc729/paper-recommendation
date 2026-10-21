"""Cấu hình kết hợp B4-B8 cho đánh giá: sinh ứng viên và đặc trưng dùng chung code với sản phẩm (recsys.pipeline).

Mọi cấu hình kết hợp xếp hạng trên CÙNG một tập ứng viên cho mỗi tác giả, nên khác biệt giữa các cấu hình chỉ đến
từ cách xếp hạng. Đánh giá tính đủ 5 chế độ trọng số cạnh (FEATURES) để so sánh.
"""
import numpy as np

from eval.protocol import Case, World
from recsys.pipeline import FEATURES, M_MAX, MODES, SOURCES, Cache, FeatureBuilder  # noqa: F401


class CachedScores:
    """Bọc điểm đã tính trên ứng viên thành cấu hình dùng được với eval.run.evaluate (ngoài ứng viên = -inf)."""

    def __init__(self, name: str, cache: Cache, scores: np.ndarray):
        self.name, self.cache, self.S = name, cache, scores
        self.row = {a: i for i, a in enumerate(cache.authors)}

    def scores(self, world: World, cases: list[Case]) -> np.ndarray:
        out = np.full((len(cases), len(world.pool)), -np.inf, dtype=np.float32)
        for k, case in enumerate(cases):
            i = self.row[case.author]
            v = self.cache.cand[i] >= 0
            out[k, self.cache.cand[i][v]] = self.S[i][v]
        return out
