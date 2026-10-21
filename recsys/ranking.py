"""Xếp hạng tuyến tính (spec mục 9.2) trên đặc trưng của từng cặp (người dùng, ứng viên).

Đặc trưng có thang rất khác nhau (cosine 0,7-0,95; số lần được trích 0-2000), nên trước khi cộng:
- đặc trưng dạng đếm / tổng (SKEWED) được nén bằng log1p(x / trung bình phần khác 0 trong danh sách ứng viên);
- rồi chuẩn hoá z trong danh sách ứng viên của từng người dùng.
Trọng số khi đó so sánh được với nhau: trọng số 0,5 nghĩa là 1 độ lệch chuẩn của đặc trưng đáng nửa độ lệch chuẩn
của độ liên quan nội dung.
"""
import numpy as np

SKEWED_PREFIXES = ("cocit", "coupling", "cites_me", "coauthor")


def standardize(F: np.ndarray, valid: np.ndarray, names: list[str]) -> np.ndarray:
    """F: (B, M, d) đặc trưng thô, valid: (B, M) ô có ứng viên -> (B, M, d) đã chuẩn hoá, ô trống = 0."""
    Z = F.astype(np.float32, copy=True)
    v = valid[..., None]
    cnt = valid.sum(axis=1, keepdims=True)[..., None].clip(min=1)
    for j, name in enumerate(names):
        if name.startswith(SKEWED_PREFIXES):
            x = np.where(valid, Z[..., j], 0)
            nz = (x > 0).sum(axis=1, keepdims=True).clip(min=1)
            mean_nz = x.sum(axis=1, keepdims=True) / nz
            Z[..., j] = np.log1p(np.divide(x, mean_nz, out=np.zeros_like(x), where=mean_nz > 0))
    Z = np.where(v, Z, 0)
    mu = Z.sum(axis=1, keepdims=True) / cnt
    sd = np.sqrt((np.where(v, Z - mu, 0) ** 2).sum(axis=1, keepdims=True) / cnt)
    Z = np.where(v, (Z - mu) / np.where(sd > 1e-9, sd, 1), 0)
    return Z.astype(np.float32)


def linear_scores(Z: np.ndarray, weights: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """-> (B, M), ô trống = -inf."""
    return np.where(valid, Z @ weights.astype(np.float32), -np.inf)
