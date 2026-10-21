"""Láng giềng cấu trúc trên đồ thị trích dẫn (spec mục 6.2), tính trực tiếp cho hồ sơ người dùng.

A (n × n, thưa): A[p, r] = trọng số cạnh p trích r (1 nếu chưa lọc, w(p, r) nếu đã lọc).
- Co-citation: hai bài hay được trích cùng nhau. Chuẩn hoá L2 theo cột: Âc, co-citation = Âcᵀ Âc (cosine).
- Coupling: hai bài trích chung reference. Chuẩn hoá L2 theo hàng: Âr, coupling = Âr Ârᵀ.
Điểm của bài p với hồ sơ x (trọng số trên các bài): Σ_r x_r · sim(p, r). Tính bằng hai phép nhân ma trận thưa
với x (Âcᵀ (Âc x)), không cần dựng cả ma trận n × n.
"""
import numpy as np
import scipy.sparse as sp


def citation_matrix(citing: np.ndarray, cited: np.ndarray, weight: np.ndarray, n: int) -> sp.csr_matrix:
    keep = weight > 0
    return sp.csr_matrix((weight[keep], (citing[keep], cited[keep])), shape=(n, n))


def _scale(m: sp.csr_matrix, axis: int) -> sp.csr_matrix:
    norm = np.sqrt(np.asarray(m.multiply(m).sum(axis=axis)).ravel())
    inv = np.divide(1.0, norm, out=np.zeros_like(norm), where=norm > 0)
    return (m @ sp.diags(inv)).tocsr() if axis == 0 else (sp.diags(inv) @ m).tocsr()


class GraphScorer:
    def __init__(self, A: sp.csr_matrix):
        self.col = _scale(A, axis=0)       # Âc
        self.col_t = self.col.T.tocsr()
        self.row = _scale(A, axis=1)       # Âr
        self.row_t = self.row.T.tocsr()

    def cocitation(self, X: np.ndarray) -> np.ndarray:
        """X: (n, b) trọng số hồ sơ của b người dùng -> (n, b)."""
        return self.col_t @ (self.col @ X)

    def coupling(self, X: np.ndarray) -> np.ndarray:
        return self.row @ (self.row_t @ X)
