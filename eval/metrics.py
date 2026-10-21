"""Độ đo (spec mục 12.2). Hàm thuần trên một danh sách đã xếp hạng, cộng bootstrap và kiểm định cặp."""
import numpy as np
from scipy import stats


def recall_at_k(hits: np.ndarray, n_rel: int, k: int) -> float:
    """hits: bool theo thứ tự xếp hạng. Tỉ lệ bài liên quan nằm trong top-k."""
    return hits[:k].sum() / n_rel


def ndcg_at_k(hits: np.ndarray, n_rel: int, k: int) -> float:
    """Nhãn nhị phân; danh sách lý tưởng xếp min(n_rel, k) bài liên quan lên đầu."""
    disc = 1 / np.log2(np.arange(2, k + 2))
    return (hits[:k] * disc[:len(hits[:k])]).sum() / disc[:min(n_rel, k)].sum()


def ndcg_graded(top_grades: np.ndarray, all_grades: np.ndarray, k: int) -> float:
    """NDCG nhiều mức, gain = 2^mức − 1. NaN nếu tác giả không có bài nào mức >= 1."""
    disc = 1 / np.log2(np.arange(2, k + 2))
    gain = 2.0 ** np.asarray(top_grades[:k], dtype=float) - 1
    ideal = 2.0 ** np.sort(np.asarray(all_grades, dtype=float))[::-1][:k] - 1
    idcg = (ideal * disc[:len(ideal)]).sum()
    return float((gain * disc[:len(gain)]).sum() / idcg) if idcg > 0 else float("nan")


def reciprocal_rank(best_rank: int) -> float:
    """best_rank: vị trí (từ 1) của bài liên quan đầu tiên trong toàn bộ xếp hạng."""
    return 1 / best_rank


def intra_list_distance(vecs: np.ndarray) -> float:
    """Trung bình 1 - cos giữa các cặp trong danh sách (vector đã chuẩn hoá L2)."""
    n = len(vecs)
    if n < 2:
        return 0.0
    sim = vecs @ vecs.T
    return float((n * n - sim.sum()) / (n * (n - 1)))   # đường chéo cos = 1 đóng góp 0


def bootstrap_ci(values: np.ndarray, n_boot: int = 1000, seed: int = 0) -> tuple[float, float]:
    """Khoảng tin cậy 95% của trung bình, lấy mẫu lại theo tác giả."""
    rng = np.random.default_rng(seed)
    means = values[rng.integers(0, len(values), (n_boot, len(values)))].mean(axis=1)
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def paired_diff(a: np.ndarray, b: np.ndarray) -> dict:
    """So sánh hai cấu hình trên cùng tập tác giả: chênh lệch trung bình b - a, CI 95%, p của Wilcoxon."""
    keep = ~(np.isnan(a) | np.isnan(b))   # độ đo nhiều mức không xác định với tác giả không có bài mức >= 1
    d = b[keep] - a[keep]
    lo, hi = bootstrap_ci(d)
    p = stats.wilcoxon(d).pvalue if np.any(d != 0) else 1.0
    return {"diff": float(d.mean()), "lo": lo, "hi": hi, "p": float(p)}
