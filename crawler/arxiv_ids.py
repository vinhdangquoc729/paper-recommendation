"""Tìm arXiv ID cho bài OpenReview theo tiêu đề (để tải .bbl lấy reference).

Thứ tự: Semantic Scholar /paper/search/match (nhanh, ~1 request/giây) rồi API tìm kiếm của arXiv
(1 request / 3 giây). Chỉ chấp nhận khi tiêu đề chuẩn hoá trùng khớp (hoặc giống >= 95%) để tránh nhận nhầm.
Cache: data/raw/arxiv/title_lookup.jsonl, resume theo forum_id; bài lỗi tạm thời được tra lại ở lần sau.
"""
import logging
import re
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

from common.config import RAW_DIR
from common.http import ApiClient, ApiError
from common.jsonl import append_jsonl, read_jsonl
from crawler import s2
from crawler.arxiv import ARXIV_BASE
from crawler.parse import norm_title

log = logging.getLogger(__name__)

LOOKUP_PATH = RAW_DIR / "arxiv" / "title_lookup.jsonl"
FINAL_STATUSES = {"found", "not_found"}
MIN_SIMILARITY = 0.95   # 0.93 còn nhận nhầm "Attention Is All..." với "Attention Is Not All..."
_ATOM = {"a": "http://www.w3.org/2005/Atom"}
_ARXIV_ABS = re.compile(r"arxiv\.org/abs/([^v\s]+)(?:v\d+)?$")


def title_match(a: str, b: str) -> float:
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    return 1.0 if na == nb else SequenceMatcher(None, na, nb).ratio()


def lookup_status() -> dict[str, dict]:
    return {r["forum_id"]: r for r in read_jsonl(LOOKUP_PATH)}


def _via_s2(client: ApiClient, title: str) -> tuple[str | None, str | None]:
    try:
        data = client.request("GET", "paper/search/match", params={"query": title, "fields": "title,externalIds"})
    except ApiError as e:
        if e.status == 404:          # "Title match not found"
            return None, None
        raise
    for p in data.get("data") or []:
        ax = (p.get("externalIds") or {}).get("ArXiv")
        if ax and title_match(title, p.get("title") or "") >= MIN_SIMILARITY:
            return ax, p.get("title")
    return None, None


def _via_arxiv(client: ApiClient, title: str) -> tuple[str | None, str | None]:
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", title).split()
    if not words:
        return None, None
    resp = client.request_raw("GET", "api/query",
                              params={"search_query": "ti:\"" + " ".join(words) + "\"", "max_results": 5})
    for entry in ET.fromstring(resp.content).findall("a:entry", _ATOM):
        found_title = " ".join((entry.findtext("a:title", "", _ATOM) or "").split())
        m = _ARXIV_ABS.search(entry.findtext("a:id", "", _ATOM) or "")
        if m and title_match(title, found_title) >= MIN_SIMILARITY:
            return m.group(1), found_title
    return None, None


def lookup_arxiv_ids(papers: list[tuple[str, str]], arxiv_interval: float = 3.0) -> int:
    """papers: [(forum_id, title)]. Ghi kết quả vào cache; trả về số bài đã tra trong lần chạy này."""
    done = lookup_status()
    todo = [(f, t) for f, t in dict(papers).items() if done.get(f, {}).get("status") not in FINAL_STATUSES]
    log.info("[arxiv-id] đã tra %d, cần tra %d bài", len(done), len(todo))
    s2_client = s2.make_client()
    ax_client = ApiClient(ARXIV_BASE, min_interval=arxiv_interval, max_retries=8, max_retry_after=None)
    found = 0
    for k, (forum_id, title) in enumerate(todo, 1):
        rec = {"forum_id": forum_id, "title": title, "arxiv_id": None, "matched_title": None, "source": None}
        try:
            ax, mt = _via_s2(s2_client, title)
            source = "s2"
            if ax is None:
                ax, mt = _via_arxiv(ax_client, title)
                source = "arxiv"
            rec.update(arxiv_id=ax, matched_title=mt, source=source if ax else None,
                       status="found" if ax else "not_found")
        except Exception as e:      # lỗi tạm thời: ghi lại, lần chạy sau tra lại
            rec["status"] = f"error_{type(e).__name__}"
            log.warning("[arxiv-id] %s: %s", forum_id, e)
        found += rec["status"] == "found"
        append_jsonl(LOOKUP_PATH, [rec])
        if k % 50 == 0 or k == len(todo):
            log.info("[arxiv-id] %d / %d, tìm thấy %d (%.0f%%)", k, len(todo), found, 100 * found / k)
    return len(todo)
