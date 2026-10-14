"""Chọn bài cần lấy reference cho giao thức đánh giá "tác giả là người dùng" (spec mục 12.1).

Reference chỉ dùng làm ground truth: các bài trong corpus mà tác giả trích ở những bài họ viết SAU mốc T.
Vì vậy chỉ cần reference của bài sau T của một mẫu tác giả, không cần cả corpus.

Tác giả đủ điều kiện: >= 2 bài trước T, >= 1 bài sau T, tổng >= 3. Các lần nộp lại cùng một bài
(trùng tiêu đề chuẩn hoá) được gộp, ngày của bài là ngày công khai sớm nhất.
"""
import json
import logging

import numpy as np
import pandas as pd

from common.config import RAW_DIR
from common.jsonl import write_jsonl_atomic

log = logging.getLogger(__name__)

EVAL_DIR = RAW_DIR / "eval"
MIN_TITLE_LEN = 20


def targets_path(t: str, n_authors: int, seed: int):
    return EVAL_DIR / f"targets_T{t}_n{n_authors}_s{seed}.jsonl"


def load_papers(conn) -> pd.DataFrame:
    """Mỗi dòng một bài (đã gộp các lần nộp): key, ngày, tác giả, các forum_id và tiêu đề."""
    df = pd.read_sql("SELECT forum_id, title, title_norm, authorids, odate, pdate, cdate FROM or_submissions", conn)
    df["date"] = df.odate.fillna(df.pdate).fillna(df.cdate)
    long_title = df.title_norm.fillna("").str.len() >= MIN_TITLE_LEN
    df["key"] = df.title_norm.where(long_title, "forum:" + df.forum_id)
    df["authors"] = df.authorids.map(lambda s: [a for a in json.loads(s or "[]") if a.startswith("~")])
    return df.groupby("key").agg(
        date=("date", "min"), title=("title", "first"), forums=("forum_id", list),
        authors=("authors", lambda col: sorted({a for lst in col for a in lst})),
    ).reset_index()


def select_targets(conn, t: str, n_authors: int, seed: int = 0) -> tuple[list[str], pd.DataFrame]:
    """-> (tác giả được chọn, bảng bài sau T của họ). Ghi lại danh sách vào data/raw/eval/ để tái lập."""
    papers = load_papers(conn)
    ap = papers[["key", "date", "authors"]].explode("authors").dropna(subset=["authors"])
    before = ap[ap.date < t].groupby("authors").size()
    after = ap[ap.date >= t].groupby("authors").size()
    cnt = pd.DataFrame({"before": before, "after": after}).fillna(0)
    eligible = sorted(cnt[(cnt.before >= 2) & (cnt.after >= 1) & (cnt.before + cnt.after >= 3)].index)
    rng = np.random.default_rng(seed)
    chosen = sorted(rng.choice(eligible, min(n_authors, len(eligible)), replace=False))
    chosen_set = set(chosen)
    target = papers[(papers.date >= t) & papers.authors.map(lambda a: bool(chosen_set & set(a)))]
    log.info("[eval] T=%s: %d tác giả đủ điều kiện, chọn %d, %d bài sau T cần reference",
             t, len(eligible), len(chosen), len(target))

    write_jsonl_atomic(targets_path(t, n_authors, seed), [
        {"kind": "meta", "T": t, "n_eligible": len(eligible), "seed": seed, "authors": chosen},
        *({"kind": "paper", "key": r.key, "date": r.date, "title": r.title, "forums": r.forums}
          for r in target.itertuples()),
    ])
    return chosen, target
