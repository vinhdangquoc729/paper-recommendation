"""Bảng `items`: mỗi bài một dòng, gốc là OpenReview, đã gộp các lần nộp lại cùng một bài.

Một bài hay bị nộp nhiều lần (reject ở ICLR rồi accept ở ICML, hoặc nộp lại ICLR năm sau).
Các bản này được gộp theo tiêu đề chuẩn hoá; bản "đại diện" là bản có kết quả tốt nhất, mới nhất.
"""
import pandas as pd

SUBMISSION_COLS = [
    "forum_id", "venue_key", "edition", "title", "title_norm", "abstract", "tldr", "keywords", "primary_area",
    "code_url", "authors", "authorids", "decision", "decision_date", "cdate", "odate", "pdate", "n_reviews",
]
_DECISION_RANK = {"accept_oral": 0, "accept_spotlight": 0, "accept_poster": 0, "accept": 0,
                  "reject": 1, "desk_rejected": 2, "withdrawn": 2}
# Được đưa vào tập ứng viên để gợi ý; withdrawn / desk-reject / đang review chỉ giữ làm dữ liệu
CANDIDATE_DECISIONS = {"accept_oral", "accept_spotlight", "accept_poster", "accept", "reject"}
MIN_TITLE_LEN = 20  # tiêu đề ngắn hơn dễ trùng nhầm ("Conclusion", "Untitled"), không gộp


def load_submissions(conn) -> pd.DataFrame:
    return pd.read_sql(f"SELECT {', '.join(SUBMISSION_COLS)} FROM or_submissions", conn)


def build_items(subs: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (items, versions). `versions` ánh xạ mọi forum_id về item_id của bản đại diện."""
    df = subs.copy()
    # ngày bài xuất hiện công khai trên OpenReview
    df["avail_date"] = df.odate.fillna(df.pdate).fillna(df.cdate)
    long_title = df.title_norm.fillna("").str.len() >= MIN_TITLE_LEN
    df["group_key"] = df.title_norm.where(long_title, "forum:" + df.forum_id)
    df["_rank"] = df.decision.map(_DECISION_RANK).fillna(3)

    df = df.sort_values(["group_key", "_rank", "edition", "n_reviews"], ascending=[True, True, False, False])
    df["item_id"] = df.groupby("group_key").forum_id.transform("first")

    versions = df[["forum_id", "item_id", "venue_key", "edition", "decision", "decision_date",
                   "avail_date"]].reset_index(drop=True)
    agg = versions.groupby("item_id").agg(first_seen=("avail_date", "min"), n_versions=("forum_id", "size"))

    items = df[df.forum_id == df.item_id].drop(columns=["group_key", "_rank", "forum_id", "title_norm"])
    items = items.join(agg, on="item_id")
    items["is_candidate"] = items.decision.isin(CANDIDATE_DECISIONS).astype(int)
    cols = ["item_id"] + [c for c in items.columns if c != "item_id"]
    return items[cols].reset_index(drop=True), versions
