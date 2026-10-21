"""Hồ sơ người dùng đa sở thích (spec mục 7.3). Hàm thuần trên embedding đã chuẩn hoá L2.

1. Phân cụm có trọng số các bài trong hồ sơ: spherical k-means (gán theo cosine), k = min(5, ⌈|P_u| / 5⌉).
2. Mỗi cụm: centroid u_c = Σ weight · e_p / ‖·‖, trọng số π_c = tổng weight của cụm (chuẩn hoá).
3. Điểm của bài p: rel_max = max_c π'_c · cos(u_c, e_p), π'_c = π_c đưa về [0,5; 1] để cụm nhỏ không bị bỏ qua.
"""
import math

import numpy as np

# Trọng số cơ sở của các tập bài trong hồ sơ (spec 7.2), nhân time decay exp(-Δt / τ)
TAU_YEARS = 3.0
W_AUTHORED, W_FIRST_AUTHOR, W_CITED, W_SAVED, W_READ = 1.0, 1.2, 0.5, 0.7, 0.3
W_INTERESTED = 0.5
# Bài từ phản hồi (lưu / quan tâm / đã đọc) chiếm tối đa chừng này lần tổng trọng số bài đã viết + đã trích;
# vượt thì co lại theo tỉ lệ. Mô phỏng 2026-10-21: không chặn thì lưu 30 bài đã kéo hồ sơ hẳn về chủ đề mới và
# các sở thích nhỏ bị đẩy khỏi top 20. Người chưa có bài (không có phần gốc) thì không chặn.
# Đang tắt (inf) để thử trên sản phẩm; 1.0 = phản hồi không nặng hơn bài đã viết + đã trích (finding.md mục 11c).
FEEDBACK_SHARE_MAX = float("inf")

K_MAX = 5
PAPERS_PER_CLUSTER = 5
PI_FLOOR = 0.5
N_ITER = 20


def _normalize(m: np.ndarray) -> np.ndarray:
    return m / np.maximum(np.linalg.norm(m, axis=-1, keepdims=True), 1e-12)


def mean_profile(vecs: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Hồ sơ một vector (B2)."""
    return _normalize((weights[:, None] * vecs).sum(axis=0))


def n_clusters(n_papers: int, k_max: int = K_MAX, per_cluster: int = PAPERS_PER_CLUSTER) -> int:
    return max(1, min(k_max, math.ceil(n_papers / per_cluster)))


def cluster_profile(vecs: np.ndarray, weights: np.ndarray, k: int | None = None,
                    seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """-> (centroid (k, d) đã chuẩn hoá, π (k,) tổng bằng 1). Cụm rỗng bị bỏ nên có thể ít hơn k cụm."""
    n = len(vecs)
    k = min(k or n_clusters(n), n)
    rng = np.random.default_rng(seed)
    p = weights / weights.sum()
    # k-means++ có trọng số: tâm sau ưu tiên bài xa các tâm đã chọn
    centers = [rng.choice(n, p=p)]
    for _ in range(1, k):
        dist = 1 - (vecs @ vecs[centers].T).max(axis=1)
        q = p * np.maximum(dist, 0)
        if q.sum() <= 0:
            break
        centers.append(rng.choice(n, p=q / q.sum()))
    cent = vecs[centers]
    assign = None
    for _ in range(N_ITER):
        new = (vecs @ cent.T).argmax(axis=1)
        if assign is not None and np.array_equal(new, assign):
            break
        assign = new
        used = np.unique(assign)
        cent = _normalize(np.stack([(weights[assign == c, None] * vecs[assign == c]).sum(axis=0) for c in used]))
        assign = np.searchsorted(used, assign)
    pi = np.bincount(assign, weights=weights, minlength=len(cent))
    return cent, pi / pi.sum()


def multi_interest_scores(cand: np.ndarray, centroids: np.ndarray, pi: np.ndarray,
                          floor: float = PI_FLOOR) -> np.ndarray:
    """rel_max cho từng ứng viên (cand: (m, d))."""
    pi_adj = floor + (1 - floor) * pi / pi.max()
    return ((cand @ centroids.T) * pi_adj).max(axis=1)
