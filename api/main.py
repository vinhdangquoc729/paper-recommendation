"""Backend FastAPI. Mọi đường dẫn nằm dưới /api; frontend (app/) gọi qua proxy của Vite khi dev."""
import math
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from api import placeholder
from api.pdf import PdfRateLimited, PdfStore, PdfUnavailable
from api.catalog import DECISION_LABELS, VENUE_LABELS, Catalog, area_label
from api.schemas import (AuthoredPaper, ConfirmBody, Facet, FeedbackBody, Meta, PaperDetail, PaperList,
                         PaperSummary, PaperVersion, Profile, ReviewSummary)
from api.userstore import UserStore

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["catalog"] = Catalog()
    state["users"] = UserStore()
    state["pdf"] = PdfStore()
    yield
    state.clear()


app = FastAPI(title="Paper Recommender API", lifespan=lifespan)


def _cat() -> Catalog:
    return state["catalog"]


def _users() -> UserStore:
    return state["users"]


SNIPPET_CHARS = 600


def _snippet(text, limit: int = SNIPPET_CHARS) -> str | None:
    text = _str(text)
    if not text or len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "…"


def _num(v) -> float | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def _str(v) -> str | None:
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)


def _summary(row: pd.Series, reasons=None, score=None) -> PaperSummary:
    users = _users()
    return PaperSummary(
        id=row.item_id, title=row.title or "", authors=row.authors, venue=VENUE_LABELS.get(row.venue_key, row.venue_key),
        year=int(row.edition), decision=_str(row.decision), primary_area=area_label(row.primary_area), tldr=_str(row.tldr), abstract_snippet=_snippet(row.abstract),
        has_code=_str(row.code_url) is not None, n_ratings=int(row.n_ratings), rating_z=_num(row.rating_z),
        quality=_num(row.quality), first_seen=_str(row.first_seen), reasons=reasons or [], score=_num(score),
        saved=row.item_id in set(users.saved_ids()), feedback=users.latest_feedback().get(row.item_id),
    )


def _page(df: pd.DataFrame, offset: int, limit: int, reasons: dict | None = None) -> list[PaperSummary]:
    page = df.iloc[offset:offset + limit]
    return [_summary(r, (reasons or {}).get(pid), r.get("score")) for pid, r in page.iterrows()]


@app.get("/api/meta", response_model=Meta)
def meta():
    df = _cat().df
    venues = df.venue_key.value_counts()
    areas = df.primary_area.dropna().value_counts()
    decisions = df.decision.dropna().value_counts()
    return Meta(
        venues=[Facet(value=k, label=VENUE_LABELS.get(k, k), count=int(n)) for k, n in venues.items()],
        years=sorted(int(y) for y in df.edition.unique()),
        areas=[Facet(value=k, label=area_label(k), count=int(n)) for k, n in areas.items()],
        decisions=[Facet(value=k, label=DECISION_LABELS.get(k, k), count=int(n)) for k, n in decisions.items()],
    )


@app.get("/api/papers", response_model=PaperList)
def list_papers(q: str = "", venue: str | None = None, year: int | None = None, decision: str | None = None,
                has_code: bool | None = None, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    """Không có q: gợi ý theo hồ sơ. Có q: tìm theo từ khoá. Bộ lọc áp dụng cho cả hai."""
    cat, users = _cat(), _users()
    df = placeholder.apply_filters(cat.df, venue, year, decision, has_code)
    if q.strip():
        hits = placeholder.search(df, q)
        return PaperList(mode="search", query=q, total=len(hits), offset=offset, items=_page(hits, offset, limit))

    fb = users.latest_feedback()
    exclude = {p for p, a in fb.items() if a in ("not_relevant", "already_read")}
    exclude |= {p for p, ok in users.authored_status().items() if ok}
    ranked, reasons = placeholder.recommend(df, users.get_profile().preferences, exclude)
    return PaperList(mode="recommend", query="", total=len(ranked), offset=offset,
                     items=_page(ranked, offset, limit, reasons))


@app.get("/api/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str):
    cat = _cat()
    row = cat.get(paper_id)
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài")
    ratings = cat.raw_ratings(paper_id)
    versions = [PaperVersion(forum_id=v.forum_id, venue=VENUE_LABELS.get(v.venue_key, v.venue_key), year=int(v.edition),
                             decision=_str(v.decision), url=f"https://openreview.net/forum?id={v.forum_id}")
                for v in cat.paper_versions(paper_id).itertuples()]
    return PaperDetail(
        **_summary(row).model_dump(),
        abstract=_str(row.abstract), keywords=row.keywords, code_url=_str(row.code_url),
        openreview_url=f"https://openreview.net/forum?id={paper_id}", pdf_url=f"https://openreview.net/pdf?id={paper_id}",
        pdf_cached=state["pdf"].is_cached(paper_id),
        reviews=ReviewSummary(n_reviews=len(ratings), ratings=ratings,
                              mean_rating=sum(ratings) / len(ratings) if ratings else None, rating_z=_num(row.rating_z)),
        versions=versions,
    )


@app.get("/api/papers/{paper_id}/related", response_model=list[PaperSummary])
def related(paper_id: str, limit: int = Query(10, ge=1, le=50)):
    """Mục "Có thể bạn quan tâm" dưới trang đọc bài."""
    cat = _cat()
    row = cat.get(paper_id)
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài")
    pairs = cat.similar_by_embedding(paper_id, limit * 2)
    reason = {"code": "similar_content"}
    if pairs is None:
        pairs, reason = placeholder.related_fallback(cat.df, row, limit), {"code": "same_area"}
    out = []
    for pid, sim in pairs:
        r = cat.get(pid)
        if r is not None and r.is_candidate == 1:
            out.append(_summary(r, [reason], sim))
    return out[:limit]


def _require_paper(paper_id: str) -> None:
    if _cat().get(paper_id) is None:
        raise HTTPException(404, "Không tìm thấy bài")


@app.post("/api/papers/{paper_id}/pdf", status_code=204)
def prepare_pdf(paper_id: str):
    """Tải PDF về cache nếu chưa có. Tốn một lượt của OpenReview (khoảng 26 lượt mỗi giờ)."""
    _require_paper(paper_id)
    try:
        state["pdf"].fetch(paper_id)
    except PdfRateLimited as e:
        raise HTTPException(429, str(e), headers={"Retry-After": str(e.retry_after_s)})
    except PdfUnavailable as e:
        raise HTTPException(404, str(e))


@app.get("/api/papers/{paper_id}/pdf")
def get_pdf(paper_id: str):
    """Trả PDF đã cache để nhúng iframe (cùng origin). Chưa cache thì 404, gọi POST trước."""
    _require_paper(paper_id)
    path = state["pdf"].path(paper_id)
    if not path.exists():
        raise HTTPException(404, "PDF chưa được tải, gọi POST /api/papers/{id}/pdf trước")
    return FileResponse(path, media_type="application/pdf",
                        headers={"Cache-Control": "private, max-age=86400",
                                 "Content-Disposition": f'inline; filename="{paper_id}.pdf"'})


@app.get("/api/me", response_model=Profile)
def get_me():
    return _users().get_profile()


@app.put("/api/me", response_model=Profile)
def put_me(profile: Profile):
    profile.openreview_id = profile.openreview_id.strip()
    return _users().save_profile(profile)


@app.get("/api/me/authored", response_model=list[AuthoredPaper])
def authored():
    """Bài trên OpenReview có authorids chứa OpenReview ID của người dùng, kèm trạng thái xác nhận."""
    users, cat = _users(), _cat()
    oid = users.get_profile().openreview_id
    if not oid:
        return []
    status = users.authored_status()
    mine = cat.df[cat.df.authorids.map(lambda ids: oid in ids)].sort_values("first_seen", ascending=False)
    return [AuthoredPaper(paper=_summary(r), confirmed=status.get(pid, True)) for pid, r in mine.iterrows()]


@app.put("/api/me/authored/{paper_id}", response_model=AuthoredPaper)
def confirm_authored(paper_id: str, body: ConfirmBody):
    row = _cat().get(paper_id)
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài")
    _users().set_authored(paper_id, body.confirmed)
    return AuthoredPaper(paper=_summary(row), confirmed=body.confirmed)


@app.get("/api/me/saved", response_model=list[PaperSummary])
def saved():
    cat = _cat()
    return [_summary(r) for pid in _users().saved_ids() if (r := cat.get(pid)) is not None]


@app.post("/api/feedback", status_code=204)
def feedback(body: FeedbackBody):
    if _cat().get(body.paper_id) is None:
        raise HTTPException(404, "Không tìm thấy bài")
    _users().add_feedback(body.paper_id, body.action)
