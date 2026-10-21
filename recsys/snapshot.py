"""Ảnh chụp dữ liệu tại một mốc thời gian T, dùng chung cho sản phẩm và đánh giá.

- Sản phẩm: T = ngày mai, pool là mọi bài đã công khai; dữ liệu nạp từ Postgres (appdb.catalog).
- Đánh giá: T là mốc quá khứ, chỉ thấy những gì có trước T; dữ liệu nạp từ data/ (eval.protocol).

Bài được đánh số 0..n-1 theo `item_ids`. `Case` là một người dùng: tác giả trong giao thức đánh giá, hoặc người dùng
thật của app (khi đó gt rỗng, cộng thêm bài đã lưu / đã đọc qua `extra` và bài cần loại qua `exclude`).
"""
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Đặc trưng ngữ cảnh trích dẫn của cạnh (or_refs, spec 5.2) và cách gộp khi một bài có nhiều mục trỏ về cùng một bài
EDGE_FEATURES = {"has_cite_info": "max", "n_mentions": "sum", "in_method": "max", "in_experiment": "max",
                 "only_in_list": "min", "appendix_only": "min"}


@dataclass
class World:
    """Dữ liệu tại mốc T. Mảng `pool` là các bài ứng viên (công khai trước T)."""
    T: str
    item_ids: np.ndarray
    first_seen: np.ndarray            # datetime64[D]
    pool: np.ndarray                  # chỉ số các bài công khai trước T
    pool_pos: np.ndarray              # chỉ số bài -> vị trí trong pool, -1 nếu không thuộc pool
    item_authors: list[list[str]]     # tác giả của bài, theo thứ tự (lấy bản có danh sách dài nhất)
    cites: dict[int, np.ndarray]      # bài -> các bài trong corpus nó trích
    has_refs: np.ndarray              # bài có lấy được reference không
    in_degree: np.ndarray             # số bài công khai trước T trích bài này
    edges: pd.DataFrame               # mỗi cạnh trích một dòng: a (bài trích), b (bài được trích), EDGE_FEATURES, grade
    emb: np.ndarray | None = None     # SPECTER2 theo thứ tự item_ids (mặc định đã trừ trung bình pool, xem center_embeddings)


@dataclass
class Case:
    """Một người dùng tại T."""
    author: str                       # OpenReview ID ("" nếu người dùng chưa có bài)
    split: str                        # train / val / test trong đánh giá, "user" với người dùng thật
    authored: np.ndarray              # bài đã viết trước T
    first_author: np.ndarray          # bool, đứng đầu bài tương ứng trong `authored`
    prior: dict[int, np.datetime64]   # bài đã trích trước T -> ngày gần nhất trích nó
    gt: np.ndarray                    # ground truth (rỗng với người dùng thật)
    n_after: int = 0                  # đánh giá: số bài viết từ T trở đi
    n_after_refs: int = 0             # đánh giá: trong đó có reference (và đúng biến thể ground truth)
    grade: np.ndarray | None = None   # đánh giá: mức 0-3 của từng bài trong gt
    extra: dict[int, float] = field(default_factory=dict)   # bài thêm vào hồ sơ (đã lưu, đã đọc) -> trọng số
    exclude: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))   # không gợi ý (đã đọc, không liên quan)
    allowed: np.ndarray | None = None   # sản phẩm: bool theo item, chỉ sinh ứng viên trong bài True (bộ lọc cứng)
    boost: np.ndarray | None = None     # sản phẩm: bool theo item, bài khớp sở thích -> thêm nguồn ứng viên "pref"

    def known(self) -> np.ndarray:
        """Bài không được gợi ý: đã viết, đã trích, đã có trong hồ sơ, hoặc người dùng loại."""
        return np.unique(np.concatenate([
            self.authored, np.fromiter(self.prior.keys(), dtype=int, count=len(self.prior)),
            np.fromiter(self.extra.keys(), dtype=int, count=len(self.extra)), self.exclude]).astype(int))


def edge_grade(edges: pd.DataFrame) -> np.ndarray:
    """Mức của một lần trích: 0 = chỉ trong cụm >= 4 khoá hoặc chỉ ở phụ lục (trích cho có);
    1 = trích bình thường; +1 nếu nhắc >= 2 lần; +1 nếu có trong Method / Experiment. Không đọc được .tex: 1."""
    if "has_cite_info" not in edges:
        return np.ones(len(edges), dtype=np.int8)
    info = edges.has_cite_info.fillna(0).to_numpy() > 0
    weak = (edges.only_in_list.fillna(0).to_numpy() > 0) | (edges.appendix_only.fillna(0).to_numpy() > 0)
    many = edges.n_mentions.fillna(1).to_numpy() >= 2
    meth = ((edges.in_method.fillna(0) > 0) | (edges.in_experiment.fillna(0) > 0)).to_numpy()
    g = np.where(weak, 0, 1 + many.astype(int) + meth.astype(int))
    return np.where(info, g, 1).astype(np.int8)


def center_embeddings(emb: np.ndarray, rows: np.ndarray, chunk: int = 20_000) -> np.ndarray:
    """Trừ vector trung bình của `rows` rồi chuẩn hoá lại độ dài (bản sao float32, không sửa `emb`).

    SPECTER2 rất bất đẳng hướng: vector trung bình của corpus dài khoảng 0,92, hai bài bất kỳ có cosine 0,88-0,95.
    Khi đó mọi phép so cosine với một hệ số nhân (hồ sơ đa sở thích: cos · π') bị hệ số lấn át phần nội dung:
    với ~Jure_Leskovec1, cả 800 ứng viên đều "thuộc" cụm lớn nhất. Trừ trung bình trả lại khoảng phân biệt."""
    mu = np.asarray(emb[rows], dtype=np.float64).mean(axis=0).astype(np.float32)
    out = np.empty(emb.shape, dtype=np.float32)
    for s in range(0, len(emb), chunk):
        x = np.asarray(emb[s:s + chunk], dtype=np.float32) - mu
        out[s:s + chunk] = x / np.linalg.norm(x, axis=1, keepdims=True).clip(min=1e-12)
    log.info("[snapshot] trừ trung bình embedding (độ dài vector trung bình %.2f)", float(np.linalg.norm(mu)))
    return out


def build_world(T: str, items: pd.DataFrame, authors: pd.DataFrame, refs: pd.DataFrame,
                emb: np.ndarray | None = None, center: bool = True) -> World:
    """items: item_id, first_seen; authors: item_id, authorids (list); refs: citing_item, cited_item (cited có thể NaN)
    và tuỳ chọn các cột EDGE_FEATURES. center: trừ trung bình embedding của pool (chỉ dùng bài trước T). Hàm thuần."""
    item_ids = items.item_id.to_numpy()
    idx = pd.Series(np.arange(len(items)), index=item_ids)
    first_seen = pd.to_datetime(items.first_seen).to_numpy().astype("datetime64[D]")
    t = np.datetime64(T)
    pool = np.flatnonzero(first_seen < t)
    pool_pos = np.full(len(items), -1)
    pool_pos[pool] = np.arange(len(pool))

    item_authors: list[list[str]] = [[] for _ in range(len(items))]
    for item, ids in zip(authors.item_id, authors.authorids):
        i = idx[item]
        if len(ids) > len(item_authors[i]):   # các bản nộp lại có thể thêm / bớt tác giả
            item_authors[i] = list(ids)

    has_refs = np.zeros(len(items), dtype=bool)
    has_refs[idx[refs.citing_item.unique()].to_numpy()] = True
    edges = refs.dropna(subset=["cited_item"])
    a = idx[edges.citing_item].to_numpy()
    b = idx[edges.cited_item].to_numpy()
    keep = a != b
    feats = {c: f for c, f in EDGE_FEATURES.items() if c in edges}
    edge_df = (pd.DataFrame({"a": a[keep], "b": b[keep], **{c: edges[c].to_numpy()[keep] for c in feats}})
               .groupby(["a", "b"], as_index=False).agg(feats) if feats else
               pd.DataFrame({"a": a[keep], "b": b[keep]}).drop_duplicates())
    a, b = a[keep], b[keep]
    order = np.lexsort((b, a))
    a, b = a[order], b[order]
    cites = {}
    for i, part in zip(*np.unique(a, return_index=True)):
        cites[int(i)] = np.unique(b[part:np.searchsorted(a, i, side="right")])

    in_degree = np.zeros(len(items))
    for i, cited in cites.items():
        if first_seen[i] < t:
            in_degree[cited] += 1
    edge_df = edge_df.reset_index(drop=True)
    edge_df["grade"] = edge_grade(edge_df)
    if emb is not None and center and len(pool):
        emb = center_embeddings(emb, pool)
    return World(T, item_ids, first_seen, pool, pool_pos, item_authors, cites, has_refs, in_degree, edge_df, emb)
