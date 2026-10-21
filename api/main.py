"""Backend FastAPI. Mọi đường dẫn nằm dưới /api; frontend (app/) gọi qua proxy của Vite khi dev.

Dữ liệu ở Postgres (appdb): catalog nạp vào bộ nhớ khi khởi động (và nạp lại khi `python -m appdb sync` đổi
catalog_meta.version); dữ liệu người dùng đọc / ghi trực tiếp. Phiên đăng nhập là cookie `session` (httponly).
"""
import logging
import math
import threading
import time
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import Cookie, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from psycopg_pool import ConnectionPool

from api import placeholder
from api.catalog import DECISION_LABELS, VENUE_LABELS, Catalog, area_label
from api.pdf import PdfRateLimited, PdfStore, PdfUnavailable
from api.schemas import (AuthoredPaper, AuthorHit, ConfirmBody, Facet, FeedbackBody, LoginAsAuthorBody, LoginBody,
                         Meta, PaperDetail, PaperList, PaperSummary, PaperVersion, Preferences, Profile, ProfilePaper,
                         RegisterBody, ReviewSummary, SessionInfo)
from api.userstore import AuthError, UserStore
from appdb import DATABASE_URL, connect
from appdb.catalog import load_catalog
from recsys.model import DEFAULT_MODEL, LinearModel
from recsys.service import Recommender, Tuning, UserHistory

log = logging.getLogger(__name__)

SESSION_COOKIE = "session"
RELOAD_CHECK_S = 60          # khoảng giữa hai lần kiểm tra catalog_meta.version
LOG_TOP = 100                # số bài đầu danh sách gợi ý ghi vào rec_items
state: dict = {}
_reload_lock = threading.Lock()


def _load() -> None:
    """Nạp catalog + bộ gợi ý (vài giây). Thiếu mô hình thì chỉ có gợi ý theo sở thích khai báo."""
    with connect() as pg:
        data = load_catalog(pg)
    state["catalog"] = Catalog(data, state["pool"])
    if DEFAULT_MODEL.exists():
        state["recommender"] = Recommender(data, LinearModel.load(DEFAULT_MODEL))
    else:
        log.warning("Chưa có %s (python -m eval ablation): chỉ gợi ý theo sở thích khai báo", DEFAULT_MODEL)
        state["recommender"] = None
    state["checked_at"] = time.monotonic()


def _maybe_reload() -> None:
    if time.monotonic() - state.get("checked_at", 0) < RELOAD_CHECK_S or not _reload_lock.acquire(blocking=False):
        return
    try:
        state["checked_at"] = time.monotonic()
        with state["pool"].connection() as pg:
            version = pg.execute("SELECT version FROM catalog_meta WHERE id = 1").fetchone()[0]
        if version != _cat().version:
            log.info("catalog đổi phiên bản %s -> %s, nạp lại", _cat().version, version)
            _load()
    finally:
        _reload_lock.release()


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["pool"] = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, kwargs={"autocommit": True}, open=True)
    _load()
    state["users"] = UserStore(state["pool"])
    state["pdf"] = PdfStore()
    yield
    state["pool"].close()
    state.clear()


app = FastAPI(title="Paper Recommender API", lifespan=lifespan)


def _cat() -> Catalog:
    return state["catalog"]


def _users() -> UserStore:
    return state["users"]


def _uid(token: str | None) -> int | None:
    return _users().user_by_token(token)


def _require_uid(token: str | None) -> int:
    uid = _uid(token)
    if uid is None:
        raise HTTPException(401, "Cần đăng nhập")
    return uid


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


class _UserView:
    """Trạng thái lưu / phản hồi của người dùng hiện tại, đọc một lần cho cả trang."""

    def __init__(self, uid: int | None):
        self.saved = set(_users().saved_ids(uid)) if uid else set()
        self.feedback = _users().latest_feedback(uid) if uid else {}


def _summary(row: pd.Series, view: _UserView, reasons=None, score=None) -> PaperSummary:
    return PaperSummary(
        id=row.item_id, title=row.title or "", authors=row.authors, venue=VENUE_LABELS.get(row.venue_key, row.venue_key),
        year=int(row.edition), decision=_str(row.decision), primary_area=area_label(row.primary_area),
        tldr=_str(row.tldr), abstract_snippet=_snippet(row.abstract),
        has_code=_str(row.code_url) is not None, n_ratings=int(row.n_ratings), rating_z=_num(row.rating_z),
        quality=_num(row.quality), first_seen=_str(row.first_seen), reasons=reasons or [], score=_num(score),
        saved=row.item_id in view.saved, feedback=view.feedback.get(row.item_id),
    )


def _page(df: pd.DataFrame, view: _UserView, offset: int, limit: int, reasons: dict | None = None) -> list[PaperSummary]:
    page = df.iloc[offset:offset + limit]
    return [_summary(r, view, (reasons or {}).get(pid), r.get("score")) for pid, r in page.iterrows()]


# ---------- phiên đăng nhập ----------
def _session_info(uid: int | None) -> SessionInfo:
    if uid is None:
        return SessionInfo(logged_in=False)
    p = _users().get_profile(uid)
    return SessionInfo(logged_in=True, display_name=p.display_name, openreview_id=p.openreview_id, email=p.email)


def _start_session(response: Response, token: str) -> SessionInfo:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=30 * 24 * 3600)
    return _session_info(_uid(token))


@app.get("/api/session", response_model=SessionInfo)
def get_session(session: str | None = Cookie(None)):
    return _session_info(_uid(session))


@app.post("/api/session/author", response_model=SessionInfo)
def login_as_author(body: LoginAsAuthorBody, response: Response):
    """Bản demo: mở tài khoản tạo sẵn của một tác giả trong corpus, không xác minh danh tính."""
    try:
        return _start_session(response, _users().login_as_author(body.openreview_id.strip()))
    except AuthError as e:
        raise HTTPException(404, str(e))


@app.post("/api/session/login", response_model=SessionInfo)
def login(body: LoginBody, response: Response):
    try:
        return _start_session(response, _users().login(body.email, body.password))
    except AuthError as e:
        raise HTTPException(401, str(e))


@app.post("/api/session/register", response_model=SessionInfo)
def register(body: RegisterBody, response: Response):
    if "@" not in body.email or len(body.password) < 8:
        raise HTTPException(422, "Email không hợp lệ hoặc mật khẩu ngắn hơn 8 ký tự")
    try:
        return _start_session(response, _users().register(body.email, body.password, body.display_name))
    except AuthError as e:
        raise HTTPException(409, str(e))


@app.delete("/api/session", status_code=204)
def logout(response: Response, session: str | None = Cookie(None)):
    if session:
        _users().logout(session)
    response.delete_cookie(SESSION_COOKIE)


@app.get("/api/authors", response_model=list[AuthorHit])
def search_authors(q: str = "", limit: int = Query(20, ge=1, le=50)):
    return [AuthorHit(**a) for a in _users().search_authors(q, limit)]


# ---------- bài báo ----------
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
                has_code: bool | None = None, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100),
                session: str | None = Cookie(None)):
    """Không có q: gợi ý theo hồ sơ (recsys; hồ sơ trống hoặc chưa đăng nhập thì theo sở thích khai báo).
    Có q: tìm theo từ khoá. Bộ lọc áp dụng cho cả hai."""
    _maybe_reload()
    cat, users = _cat(), _users()
    uid = _uid(session)
    view = _UserView(uid)
    if q.strip():
        hits = placeholder.search(placeholder.apply_filters(cat.df, venue, year, decision, has_code), q)
        return PaperList(mode="search", query=q, total=len(hits), offset=offset, items=_page(hits, view, offset, limit))

    prefs = users.get_profile(uid).preferences if uid else Preferences()
    allowed = placeholder.recommend_filter(cat.df, prefs, venue, year, decision, has_code)
    rec = state["recommender"]
    tuning = Tuning(freshness=prefs.freshness, diversity=prefs.diversity, areas=set(prefs.areas), keywords=prefs.keywords)
    # catalog.df và Recommender cùng thứ tự bài (catalog.papers), nên mặt nạ truyền thẳng được
    history = users.history(uid) if uid else UserHistory()
    recs = rec.recommend(history, tuning, allowed.to_numpy()) if uid and rec else None
    if recs is None:
        ranked, reasons = placeholder.recommend(cat.df[allowed], prefs, history.hidden)
        return PaperList(mode="recommend", query="", total=len(ranked), offset=offset,
                         items=_page(ranked, view, offset, limit, reasons))

    by_id = {r.paper_id: r for r in recs}
    ranked = cat.df.loc[list(by_id)].assign(score=[r.score for r in recs])     # recs đã xếp hạng (kể cả MMR)
    if offset == 0:
        users.log_recommendations(uid, "feed", rec.model.name, cat.version,
                                  [by_id[p] for p in ranked.item_id[:LOG_TOP]])
    reasons = {p: [_reason_label(x) for x in by_id[p].reasons] for p in ranked.item_id[offset:offset + limit]}
    return PaperList(mode="recommend", query="", total=len(ranked), offset=offset,
                     items=_page(ranked, view, offset, limit, reasons))


def _reason_label(r: dict) -> dict:
    """recsys trả mã lĩnh vực thô ('deep_learning->llm'), giao diện cần nhãn."""
    if r["code"] == "area_match":
        return {**r, "params": {**r["params"], "area": area_label(r["params"].get("area"))}}
    return r


@app.get("/api/papers/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str, session: str | None = Cookie(None)):
    cat = _cat()
    row = cat.get(paper_id)
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài")
    ratings = cat.raw_ratings(paper_id)
    versions = [PaperVersion(forum_id=v.forum_id, venue=VENUE_LABELS.get(v.venue_key, v.venue_key), year=int(v.edition),
                             decision=_str(v.decision), url=f"https://openreview.net/forum?id={v.forum_id}")
                for v in cat.paper_versions(paper_id).itertuples()]
    return PaperDetail(
        **_summary(row, _UserView(_uid(session))).model_dump(),
        abstract=_str(row.abstract), keywords=row.keywords, code_url=_str(row.code_url),
        openreview_url=f"https://openreview.net/forum?id={paper_id}", pdf_url=f"https://openreview.net/pdf?id={paper_id}",
        pdf_cached=state["pdf"].is_cached(paper_id), arxiv_id=_str(row.get("arxiv_id")),
        reviews=ReviewSummary(n_reviews=len(ratings), ratings=ratings,
                              mean_rating=sum(ratings) / len(ratings) if ratings else None, rating_z=_num(row.rating_z)),
        versions=versions,
    )


@app.get("/api/papers/{paper_id}/related", response_model=list[PaperSummary])
def related(paper_id: str, limit: int = Query(10, ge=1, le=50), session: str | None = Cookie(None)):
    """Mục "Có thể bạn quan tâm" dưới trang đọc bài: recsys.related (nội dung, đồ thị trích dẫn, tác giả, hồ sơ);
    không có bộ gợi ý thì theo embedding."""
    cat = _cat()
    row = cat.get(paper_id)
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài")
    uid = _uid(session)
    view = _UserView(uid)
    rec = state["recommender"]
    if rec is not None:
        users = _users()
        prefs = users.get_profile(uid).preferences if uid else Preferences()
        recs = rec.related(paper_id, users.history(uid) if uid else UserHistory(), limit, prefs.diversity)
        if recs is not None:
            return [_summary(cat.get(r.paper_id), view, [_reason_label(x) for x in r.reasons], r.score) for r in recs]
    pairs = cat.similar_by_embedding(paper_id, limit * 2)
    reason = {"code": "similar_content"}
    if pairs is None:
        pairs, reason = placeholder.related_fallback(cat.df, row, limit), {"code": "same_area"}
    out = []
    for pid, sim in pairs:
        r = cat.get(pid)
        if r is not None and r.is_candidate == 1:
            out.append(_summary(r, view, [reason], sim))
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


# ---------- tài khoản (cần đăng nhập) ----------
@app.get("/api/me", response_model=Profile)
def get_me(session: str | None = Cookie(None)):
    return _users().get_profile(_require_uid(session))


@app.put("/api/me", response_model=Profile)
def put_me(profile: Profile, session: str | None = Cookie(None)):
    try:
        return _users().save_profile(_require_uid(session), profile)
    except AuthError as e:
        raise HTTPException(409, str(e))


@app.get("/api/me/authored", response_model=list[AuthoredPaper])
def authored(session: str | None = Cookie(None)):
    """Bài trên OpenReview có tên người dùng (theo OpenReview ID) và bài tự thêm, kèm trạng thái xác nhận."""
    uid = _require_uid(session)
    users, cat = _users(), _cat()
    oid = users.openreview_id(uid)
    status = users.authored_status(uid)
    mine = cat.df[cat.df.authorids.map(lambda ids: oid in ids)] if oid else cat.df.iloc[:0]
    manual = [p for p, ok in status.items() if ok and p not in mine.index and p in cat.df.index]
    mine = pd.concat([mine, cat.df.loc[manual]]).sort_values("first_seen", ascending=False)
    view = _UserView(uid)
    return [AuthoredPaper(paper=_summary(r, view), confirmed=status.get(pid, True)) for pid, r in mine.iterrows()]


@app.put("/api/me/authored/{paper_id}", response_model=AuthoredPaper)
def confirm_authored(paper_id: str, body: ConfirmBody, session: str | None = Cookie(None)):
    uid = _require_uid(session)
    row = _cat().get(paper_id)
    if row is None:
        raise HTTPException(404, "Không tìm thấy bài")
    _users().set_authored(uid, paper_id, body.confirmed)
    return AuthoredPaper(paper=_summary(row, _UserView(uid)), confirmed=body.confirmed)


@app.get("/api/me/saved", response_model=list[PaperSummary])
def saved(session: str | None = Cookie(None)):
    uid = _require_uid(session)
    cat, view = _cat(), _UserView(uid)
    return [_summary(r, view) for pid in _users().saved_ids(uid) if (r := cat.get(pid)) is not None]


@app.get("/api/me/profile-papers", response_model=list[ProfilePaper])
def profile_papers(session: str | None = Cookie(None)):
    """Mọi bài bộ gợi ý đang dùng làm hồ sơ (đã viết, đã trích, đã lưu, đã đọc), kèm trọng số thật."""
    uid = _require_uid(session)
    rec, cat = state["recommender"], _cat()
    if rec is None:
        return []
    view = _UserView(uid)
    return [ProfilePaper(paper=_summary(r, view), roles=roles, weight=round(w, 4))
            for pid, roles, w in rec.profile_items(_users().history(uid)) if (r := cat.get(pid)) is not None]


@app.post("/api/feedback", status_code=204)
def feedback(body: FeedbackBody, session: str | None = Cookie(None)):
    uid = _require_uid(session)
    if _cat().get(body.paper_id) is None:
        raise HTTPException(404, "Không tìm thấy bài")
    _users().add_event(uid, body.paper_id, body.action)
