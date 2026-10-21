"""Xếp hạng lại để đa dạng hoá (spec mục 10.1): MMR.

    p* = argmax_{p ∈ R \\ S} [ λ · score(p) − (1 − λ) · max_{s ∈ S} cos(e_p, e_s) ]

score được đưa về [0, 1] trong danh sách R để cùng thang với cosine.
"""
import numpy as np

LAMBDA = 0.7


def mmr(scores: np.ndarray, emb: np.ndarray, k: int, lam: float = LAMBDA) -> np.ndarray:
    """scores (m,), emb (m, d) đã chuẩn hoá L2 -> chỉ số k phần tử được chọn theo thứ tự."""
    m = len(scores)
    k = min(k, m)
    lo, hi = scores.min(), scores.max()
    rel = (scores - lo) / (hi - lo) if hi > lo else np.zeros(m)
    sim = emb @ emb.T
    chosen = [int(np.argmax(rel))]
    max_sim = sim[chosen[0]].copy()
    taken = np.zeros(m, dtype=bool)
    taken[chosen[0]] = True
    for _ in range(1, k):
        val = np.where(taken, -np.inf, lam * rel - (1 - lam) * max_sim)
        j = int(np.argmax(val))
        chosen.append(j)
        taken[j] = True
        max_sim = np.maximum(max_sim, sim[j])
    return np.array(chosen)
