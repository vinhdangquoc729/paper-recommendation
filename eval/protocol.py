"""Giao thức đánh giá "tác giả là người dùng" (spec mục 12.1).

Quay lại mốc T, coi mỗi tác giả là một người dùng:
- hệ thống chỉ biết những gì có trước T: pool ứng viên là các bài đã công khai trước T, hồ sơ là bài tác giả viết
  trước T và các bài họ trích trong đó, mọi thống kê (số lần được trích, q_p) chỉ tính từ dữ liệu trước T;
- ground truth là các bài trong pool mà tác giả trích ở những bài họ viết từ T trở đi, trừ bài họ đã trích trước T
  (đã biết rồi) và bài của chính họ.

Ground truth dùng MỌI cạnh trích, không lọc theo trọng số w của V3: lọc bằng w thì cấu hình dùng w được chấm
bằng chính thước đo của nó. Biến thể `lead` chỉ tính bài mà tác giả đứng đầu hoặc cuối (người chọn reference).
Biến thể `novel` bỏ thêm bài do cộng sự trước T viết: trên val, bài của cộng sự chiếm 7% ground truth, gấp 23 lần tỉ lệ
trong pool (trích trong nhóm), nên `all` thưởng cho việc gợi ý bài người dùng gần như chắc chắn đã biết.

Mỗi bài ground truth còn có MỨC 0-3 theo cách bài sau T của tác giả trích nó (edge_grade), dùng cho NDCG nhiều mức.
Mức chỉ dựa trên ngữ cảnh tác giả viết (số lần nhắc, section, cụm trích, phụ lục), không dùng độ giống nội dung hay
độ phổ biến, để không tự thiên vị phương pháp nội dung hay phạt bài nổi tiếng theo định nghĩa.

Đơn vị là item của module features (đã gộp các lần nộp lại), ngày của bài là `first_seen`. World, Case, build_world
nằm ở recsys.snapshot (dùng chung với sản phẩm).
"""
import logging
import zlib

import numpy as np

from features.graph_inputs import load_inputs
from recsys.snapshot import EDGE_FEATURES, Case, World, build_world, edge_grade  # noqa: F401 (dùng lại ở eval)

log = logging.getLogger(__name__)

MIN_BEFORE = 2                                   # số bài tối thiểu trước T để dựng được hồ sơ
SPLITS = (("train", 60), ("val", 20), ("test", 20))
GT_VARIANTS = ("all", "lead", "novel")


def split_of(author: str) -> str:
    """Chia tác giả cố định theo crc32 của ID: không phụ thuộc T hay thứ tự dữ liệu."""
    h = zlib.crc32(author.encode()) % 100
    for name, share in SPLITS:
        if h < share:
            return name
        h -= share
    raise AssertionError


def build_cases(world: World, variant: str = "all") -> list[Case]:
    if variant not in GT_VARIANTS:
        raise ValueError(variant)
    t = np.datetime64(world.T)
    by_author: dict[str, list[int]] = {}
    for i, ids in enumerate(world.item_authors):
        for a in ids:
            if a.startswith("~"):
                by_author.setdefault(a, []).append(i)

    empty = np.array([], dtype=int)
    grade_of = dict(zip(zip(world.edges.a.to_numpy(), world.edges.b.to_numpy()), world.edges.grade.to_numpy()))
    cases = []
    for author, items in by_author.items():
        before = [i for i in items if world.first_seen[i] < t]
        after = [i for i in items if world.first_seen[i] >= t]
        if len(before) < MIN_BEFORE or not after:
            continue
        lead = [i for i in after if world.item_authors[i][0] == author or world.item_authors[i][-1] == author]
        source = [i for i in (lead if variant == "lead" else after) if world.has_refs[i]]
        coauthors = {a for i in before for a in world.item_authors[i]} - {author} if variant == "novel" else set()
        prior: dict[int, np.datetime64] = {}
        for i in before:
            for r in world.cites.get(i, empty):
                prior[int(r)] = max(prior.get(int(r), world.first_seen[i]), world.first_seen[i])
        best: dict[int, int] = {}      # bài -> mức cao nhất qua các bài sau T
        n_strong: dict[int, int] = {}  # bài -> số bài sau T trích nó với mức >= 1
        for i in source:
            for r in world.cites.get(i, empty):
                g = int(grade_of.get((i, int(r)), 1))
                best[int(r)] = max(best.get(int(r), 0), g)
                n_strong[int(r)] = n_strong.get(int(r), 0) + (g >= 1)
        gt = sorted(r for r in best
                    if world.pool_pos[r] >= 0 and r not in prior and author not in world.item_authors[r]
                    and not coauthors.intersection(world.item_authors[r]))
        if not gt:
            continue
        # được >= 2 bài sau T của tác giả trích (không phải cho có): quan tâm bền, mức cao nhất
        grade = np.array([3 if n_strong[r] >= 2 else best[r] for r in gt], dtype=np.int8)
        cases.append(Case(author, split_of(author), np.array(before),
                          np.array([world.item_authors[i][0] == author for i in before]),
                          prior, np.array(gt), len(after), len(source), grade))
    return cases


def load_world(conn, T: str, with_emb: bool = True, center: bool = True) -> World:
    items, authors, refs, emb = load_inputs(conn, with_emb)
    w = build_world(T, items, authors, refs, emb, center=center)
    log.info("[eval] T=%s: %d bài, pool %d, %d bài có reference, %d cạnh trích trong corpus",
             T, len(w.item_ids), len(w.pool), w.has_refs.sum(), sum(len(c) for c in w.cites.values()))
    return w
