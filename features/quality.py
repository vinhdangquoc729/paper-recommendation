"""Điểm chất lượng q_p (spec mục 6.3), chỉ dùng dữ liệu OpenReview: review, decision, link code.

Có tham số `as_of` để tính lại tại một mốc thời gian T khi đánh giá: chỉ dùng review và decision
đã công khai trước T, và thống kê chuẩn hoá z cũng chỉ tính trên các review đó (tránh rò rỉ dữ liệu).
"""
import numpy as np
import pandas as pd

M_PRIOR = 3                  # Bayesian average: kéo về 0 như thể có thêm m review trung bình
MIN_GROUP_REVIEWS = 30       # venue-năm ít review hơn thì không chuẩn hoá z được
DECISION_BONUS = {"accept_oral": 1.0, "accept_spotlight": 0.7, "accept_poster": 0.4, "accept": 0.4,
                  "reject": 0.0, "desk_rejected": -0.2, "withdrawn": -0.2}
UNKNOWN_DECISION_BONUS = 0.2
WEIGHTS = {"review": 0.5, "decision": 0.3, "code": 0.1}
# Venue công khai review ngay trong lúc chấm; các venue khác chỉ công khai sau khi có decision
OPEN_REVIEW_VENUES = {"iclr", "tmlr"}


def load_reviews(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT forum_id, rating, confidence, cdate FROM or_reviews", conn)


def _visible_date(df: pd.DataFrame, own_date: str) -> pd.Series:
    """Ngày một review / decision thực sự công khai."""
    # ngày dạng chuỗi ISO nên so sánh chuỗi là đủ; "" = thiếu
    known_after_decision = df[[own_date, "decision_date", "avail_date"]].fillna("").max(axis=1).replace("", None)
    return df[own_date].where(df.venue_key.isin(OPEN_REVIEW_VENUES), known_after_decision)


def review_scores(reviews: pd.DataFrame, versions: pd.DataFrame, as_of: str | None = None) -> pd.DataFrame:
    """Rating -> z theo venue-năm -> trung bình có trọng số confidence -> Bayesian average, theo item."""
    r = reviews.merge(versions, on="forum_id")
    r["visible"] = _visible_date(r, "cdate")
    if as_of:
        r = r[r.visible < as_of]
    r = r.dropna(subset=["rating"])
    g = r.groupby(["venue_key", "edition"])
    mu, sd, cnt = g.rating.transform("mean"), g.rating.transform("std"), g.rating.transform("size")
    r = r.assign(z=(r.rating - mu) / sd)[(cnt >= MIN_GROUP_REVIEWS) & (sd > 0)]
    # confidence có thang khác nhau giữa venue: đưa về tỉ lệ so với trung bình của venue-năm
    w = r.confidence / r.groupby(["venue_key", "edition"]).confidence.transform("mean")
    r = r.assign(w=w.fillna(1.0), wz=w.fillna(1.0) * r.z)

    out = r.groupby("item_id").agg(n_ratings=("z", "size"), sum_w=("w", "sum"), sum_wz=("wz", "sum"))
    out["rating_z"] = out.sum_wz / out.sum_w
    out["q_review"] = out.n_ratings * out.rating_z / (out.n_ratings + M_PRIOR)
    return out[["n_ratings", "rating_z", "q_review"]]


def decision_bonus(versions: pd.DataFrame, as_of: str | None = None) -> pd.Series:
    """Kết quả tốt nhất trong các bản đã có decision trước as_of (bản reject cũ vẫn tính nếu bản accept chưa có)."""
    v = versions.dropna(subset=["decision"])
    if as_of:
        # venue không công bố note Decision (ICML 2023-24): biết kết quả từ lúc bài accept được công khai
        known = v.decision_date.fillna(v.avail_date)
        v = v[known < as_of]
    return v.assign(bonus=v.decision.map(DECISION_BONUS)).groupby("item_id").bonus.max()


def compute_quality(items: pd.DataFrame, versions: pd.DataFrame, reviews: pd.DataFrame,
                    as_of: str | None = None) -> pd.DataFrame:
    q = items[["item_id", "venue_key", "edition", "code_url", "first_seen"]].set_index("item_id")
    q = q.join(review_scores(reviews, versions, as_of))
    q["bonus_dec"] = decision_bonus(versions, as_of).reindex(q.index)
    q["decision_known"] = q.bonus_dec.notna().astype(int)
    q["bonus_dec"] = q.bonus_dec.fillna(UNKNOWN_DECISION_BONUS)

    # Link code chỉ có nghĩa ở venue-năm có hỏi trường này (ICML 2025+, TMLR); ở venue khác coi là thiếu
    asks_code = q.groupby(["venue_key", "edition"]).code_url.transform(lambda s: s.notna().any())
    q["has_code"] = q.code_url.notna().astype(float).where(asks_code)
    if as_of:
        q.loc[q.first_seen >= as_of, "has_code"] = np.nan

    parts = {
        "review": 1 / (1 + np.exp(-q.q_review)),
        "decision": q.bonus_dec,
        "code": q.has_code,
    }
    num = sum(WEIGHTS[k] * v.fillna(0) for k, v in parts.items())
    den = sum(WEIGHTS[k] * v.notna() for k, v in parts.items())
    q["q"] = (num / den).clip(0, 1)
    q["n_ratings"] = q.n_ratings.fillna(0).astype(int)
    return q.drop(columns=["venue_key", "edition", "code_url", "first_seen"]).reset_index()
