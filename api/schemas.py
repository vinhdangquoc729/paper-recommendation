"""Hợp đồng dữ liệu giữa backend và frontend (app/src/types.ts phải khớp với file này)."""
from typing import Literal

from pydantic import BaseModel, Field

FeedbackAction = Literal["relevant", "not_relevant", "already_read", "saved", "unsaved", "clicked"]


class PaperSummary(BaseModel):
    id: str
    title: str
    authors: list[str]
    venue: str                     # "ICLR"
    year: int
    decision: str | None           # accept_oral / accept_spotlight / accept_poster / accept / reject / ...
    primary_area: str | None
    tldr: str | None
    abstract_snippet: str | None = None   # abstract đã cắt ngắn, cho khung xem nhanh khi hover
    has_code: bool
    n_ratings: int
    rating_z: float | None         # điểm review chuẩn hoá theo venue-năm
    quality: float | None          # q_p trong [0, 1]
    first_seen: str | None         # ngày bài công khai sớm nhất
    reasons: list[str] = []        # "Vì sao gợi ý bài này"
    score: float | None = None
    saved: bool = False
    feedback: FeedbackAction | None = None


class PaperList(BaseModel):
    mode: Literal["recommend", "search"]
    query: str
    total: int
    offset: int
    items: list[PaperSummary]


class PaperVersion(BaseModel):
    forum_id: str
    venue: str
    year: int
    decision: str | None
    url: str


class ReviewSummary(BaseModel):
    n_reviews: int
    ratings: list[float]           # điểm gốc theo thang của venue
    mean_rating: float | None
    rating_z: float | None


class PaperDetail(PaperSummary):
    abstract: str | None
    keywords: list[str]
    code_url: str | None
    openreview_url: str
    pdf_url: str                   # link gốc trên OpenReview (mở tab mới)
    pdf_cached: bool               # đã có trong cache, nhúng được ngay mà không tốn lượt tải
    reviews: ReviewSummary
    versions: list[PaperVersion]


class Preferences(BaseModel):
    areas: list[str] = []          # primary_area quan tâm
    venues: list[str] = []         # rỗng = mọi venue
    keywords: list[str] = []
    year_from: int | None = None
    include_rejected: bool = False
    only_with_code: bool = False
    freshness: float = Field(0.5, ge=0, le=1)   # 0 = kinh điển, 1 = mới
    diversity: float = Field(0.3, ge=0, le=1)   # 0 = sát chủ đề, 1 = đa dạng


class Profile(BaseModel):
    display_name: str = ""
    email: str = ""
    openreview_id: str = ""        # dạng ~Ten_Ho1
    preferences: Preferences = Preferences()


class AuthoredPaper(BaseModel):
    paper: PaperSummary
    confirmed: bool


class ConfirmBody(BaseModel):
    confirmed: bool


class FeedbackBody(BaseModel):
    paper_id: str
    action: FeedbackAction


class Facet(BaseModel):
    value: str
    label: str
    count: int


class Meta(BaseModel):
    venues: list[Facet]
    years: list[int]
    areas: list[Facet]
    decisions: list[Facet]
