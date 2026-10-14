"""Logic gợi ý TẠM THỜI, chỉ để giao diện có dữ liệu thật mà hiển thị.

Sẽ được thay bằng module recsys (hồ sơ đa sở thích, sinh ứng viên, xếp hạng, MMR) theo spec Khối 3 đến 6.
Giữ nguyên chữ ký các hàm để main.py không phải đổi.
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


def recommend(df: pd.DataFrame, prefs: Preferences, exclude: set[str]) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Tạm: điểm = chất lượng x độ mới, cộng điểm nếu khớp lĩnh vực / từ khoá trong preference."""
    df = df[(df.is_candidate == 1) & ~df.item_id.isin(exclude)]
    if not prefs.include_rejected:
        df = df[df.decision.isin(ACCEPTED)]
    if prefs.only_with_code:
        df = df[df.code_url.notna()]
    if prefs.venues:
        df = df[df.venue_key.isin(prefs.venues)]
    if prefs.year_from:
        df = df[df.edition >= prefs.year_from]

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
            r.append(f"Thuộc lĩnh vực bạn quan tâm: {area_label(row.primary_area)}")
        if kw_hit.get(pid):
            r.append("Khớp từ khoá: " + ", ".join(kw_hit[pid][:3]))
        if row.decision in ("accept_oral", "accept_spotlight"):
            r.append(f"{DECISION_LABELS[row.decision]} tại {VENUE_LABELS[row.venue_key]} {row.edition}")
        elif (row.rating_z or 0) > 0.8:
            r.append("Điểm review cao so với cùng hội nghị")
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
