"""Trọng số cạnh trích dẫn w(p, r) (spec mục 5.3, V3): reference nào thực sự liên quan tới bài trích nó.

    s(p, r) = c·log(1 + n_mentions) + d·[trích trong Method / Experiment] − e·[chỉ nằm trong cite >= 4 khoá]
            − g·[chỉ trích trong phụ lục] + f·sim_z(p, r) + bias
    w(p, r) = σ(s) · idf(r),   idf(r) = log(N / (1 + deg_in(r))) / log(N)

Khác spec: chưa có is_influential / intent (cần S2), thay bằng đặc trưng từ .tex (or_refs); content_sim
SPECTER2 dồn trong khoảng 0,7-0,95 nên dùng dạng chuẩn hoá z trên mọi cạnh. Hệ số đặt tay, chưa học từ nhãn.
Cạnh không đọc được .tex (has_cite_info = 0) coi như nhắc 1 lần, không có thông tin section.

`edge_weights(mode=...)` cho ablation: raw (mọi cạnh 1), idf (chỉ phạt hub), ctx (chỉ ngữ cảnh), w (cả hai),
w_theta (w rồi bỏ cạnh w < θ_edge). Hàm thuần.
"""
import numpy as np
import pandas as pd

COEF = {"mentions": 0.5, "method": 0.5, "list": 0.5, "appendix": 0.5, "sim": 1.0}
BIAS = 0.0
THETA_EDGE = 0.3
MODES = ("raw", "idf", "ctx", "w", "w_theta")


def idf(deg_in: np.ndarray, n_citing: int) -> np.ndarray:
    return np.clip(np.log(n_citing / (1 + deg_in)) / np.log(n_citing), 0, 1)


def context_score(edges: pd.DataFrame, sim: np.ndarray) -> np.ndarray:
    """σ(s) theo ngữ cảnh trích dẫn và độ giống nội dung, trong [0, 1]."""
    info = edges.has_cite_info.fillna(0).to_numpy() > 0
    mentions = np.where(info, edges.n_mentions.fillna(1).to_numpy(), 1)
    method = info & ((edges.in_method.fillna(0) > 0) | (edges.in_experiment.fillna(0) > 0)).to_numpy()
    only_list = info & (edges.only_in_list.fillna(0).to_numpy() > 0)
    appendix = info & (edges.appendix_only.fillna(0).to_numpy() > 0)
    sim_z = (sim - sim.mean()) / max(sim.std(), 1e-9)
    s = (COEF["mentions"] * np.log1p(mentions) + COEF["method"] * method - COEF["list"] * only_list
         - COEF["appendix"] * appendix + COEF["sim"] * sim_z + BIAS)
    return 1 / (1 + np.exp(-s))


def edge_weights(edges: pd.DataFrame, sim: np.ndarray, deg_in: np.ndarray, n_citing: int,
                 mode: str = "w", theta: float = THETA_EDGE) -> np.ndarray:
    """edges: các cột của or_refs (đã gộp theo cạnh) + `b` (chỉ số bài được trích); deg_in theo chỉ số bài."""
    if mode == "raw":
        return np.ones(len(edges))
    i = idf(deg_in[edges.b.to_numpy()], n_citing)
    if mode == "idf":
        return i
    ctx = context_score(edges, sim)
    if mode == "ctx":
        return ctx
    w = ctx * i
    if mode == "w":
        return w
    if mode == "w_theta":
        return np.where(w >= theta, w, 0.0)
    raise ValueError(mode)
