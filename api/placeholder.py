"""Phần gợi ý không cần hồ sơ: bộ lọc, tìm kiếm theo từ khoá, và gợi ý cold-start theo sở thích khai báo.

Người dùng có bài (đã viết, đã lưu, đã đọc) được gợi ý bằng recsys.service; file này chỉ dùng khi hồ sơ còn trống
(spec 7.4 tầng 3) hoặc chưa đăng nhập.
"""
import numpy as np
import pandas as pd

from api.catalog import DECISION_LABELS, VENUE_LABELS, area_label
from api.schemas import Preferences

ACCEPTED = {"accept_oral", "accept_spotlight", "accept_poster", "accept"}


def apply_filters(df: pd.DataFrame, venue: str | None, year: int | None, decision: str | None,
                  has_code: bool | None) -> pd.DataFrame:
    if venue:
        df = df[df.venue_key == venue]
    if year:
        df = df[df.edition == year]
    if decision == "accepted":
        df = df[df.decision.isin(ACCEPTED)]
    elif decision:
        df = df[df.decision == decision]
    if has_code:
        df = df[df.code_url.notna()]
    return df


def recommend_filter(df: pd.DataFrame, prefs: Preferences, venue: str | None, year: int | None,
                     decision: str | None, has_code: bool | None) -> pd.Series:
    """Bộ lọc cứng cho gợi ý: bộ lọc trên trang gộp với sở thích khai báo. Cùng một tiêu chí mà hai bên đều đặt thì
    bộ lọc trên trang thắng (chọn "Reject" trên trang vẫn ra bài reject dù sở thích chỉ lấy bài được nhận)."""
    mask = pd.Series(True, index=df.index)
    if venue:
        mask &= df.venue_key == venue
    elif prefs.venues:
        mask &= df.venue_key.isin(prefs.venues)
    if year:
        mask &= df.edition == year
    elif prefs.year_from:
        mask &= df.edition >= prefs.year_from
    if decision == "accepted":
        mask &= df.decision.isin(ACCEPTED)
    elif decision:
        mask &= df.decision == decision
    elif not prefs.include_rejected:
        mask &= df.decision.isin(ACCEPTED)
    if has_code or prefs.only_with_code:
        mask &= df.code_url.notna()
    return mask


def recommend(df: pd.DataFrame, prefs: Preferences, exclude: set[str]) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Cold-start (chưa đăng nhập, hoặc hồ sơ chưa có bài nào): điểm = chất lượng x độ mới, cộng điểm nếu khớp
    lĩnh vực / từ khoá trong sở thích khai báo. df đã qua recommend_filter."""
    df = df[(df.is_candidate == 1) & ~df.item_id.isin(exclude)]

    newest = pd.to_datetime(df.first_seen).max()
    age_days = (newest - pd.to_datetime(df.first_seen)).dt.days.clip(lower=0)
    half_life = 60 + (1 - prefs.freshness) * 900          # freshness cao -> ưu tiên bài mới mạnh hơn
    fresh = np.exp(-age_days / half_life)
    area_hit = df.primary_area.isin(prefs.areas) if prefs.areas else pd.Series(False, index=df.index)
    kw = [k.lower() for k in prefs.keywords if k.strip()]
    kw_hit = df.search_text.map(lambda t: [k for k in kw if k in t]) if kw else pd.Series([[]] * len(df), index=df.index)
    score = df.quality.fillna(0.3) * fresh + 0.3 * area_hit + 0.2 * kw_hit.map(bool)

    ranked = df.assign(score=score).sort_values("score", ascending=False)
    reasons = {}
    for pid, row in ranked.head(500).iterrows():
        r = []
        if area_hit.get(pid):
            r.append({"code": "area_match", "params": {"area": area_label(row.primary_area)}})
        if kw_hit.get(pid):
            r.append({"code": "keyword_match", "params": {"keywords": ", ".join(kw_hit[pid][:3])}})
        if row.decision in ("accept_oral", "accept_spotlight"):
            r.append({"code": "strong_decision", "params": {"decision": DECISION_LABELS[row.decision],
                                                            "venue": VENUE_LABELS[row.venue_key],
                                                            "year": int(row.edition)}})
        elif (row.rating_z or 0) > 0.8:
            r.append({"code": "high_review"})
        reasons[pid] = r[:2]
    return ranked, reasons


def search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Tạm: mọi từ phải xuất hiện trong tiêu đề, abstract hoặc keywords; từ khớp tiêu đề được ưu tiên."""
    terms = [t for t in query.lower().split() if t]
    mask = pd.Series(True, index=df.index)
    for t in terms:
        mask &= df.search_text.str.contains(t, regex=False)
    hits = df[mask]
    in_title = sum(hits.search_title.str.contains(t, regex=False).astype(int) for t in terms)
    score = in_title + hits.quality.fillna(0)
    return hits.assign(score=score).sort_values("score", ascending=False)


def related_fallback(df: pd.DataFrame, paper: pd.Series, k: int) -> list[tuple[str, float]]:
    """Khi chưa có embedding: bài cùng lĩnh vực (thiếu lĩnh vực thì cùng hội nghị-năm), chất lượng cao."""
    if isinstance(paper.primary_area, str):
        same = df[df.primary_area == paper.primary_area]
    else:
        same = df[(df.venue_key == paper.venue_key) & (df.edition == paper.edition)]
    same = same[(same.item_id != paper.item_id) & (same.is_candidate == 1)]
    top = same.sort_values("quality", ascending=False).head(k)
    return [(pid, None) for pid in top.item_id]
