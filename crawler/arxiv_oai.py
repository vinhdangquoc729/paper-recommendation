"""Tìm arXiv ID hàng loạt: tải metadata arXiv qua OAI-PMH rồi ghép tiêu đề + tác giả ngay trên máy.

Thay cho tra từng bài (arxiv_ids.py, 3 đến 4 giây một bài, khoảng 30 giờ cho 2026). Cách này bù được bài bị reject /
rút mà S2 không gắn vào venue (trước đó 0% có arXiv ID).

1. harvest: ListRecords (metadataPrefix=arXiv) theo set (mặc định cs, gồm cả bài cross-list sang cs) và theo từng
   tháng của datestamp (ngày cập nhật cuối); mỗi trang khoảng 1300 bản ghi. Mỗi tháng một file
   data/raw/arxiv/oai/{set}_{YYYY-MM}.jsonl, xong thì thêm file .done; tháng dở dang được tải lại từ đầu
   (resumptionToken hết hạn trong ngày nên không lưu). Tháng hiện tại không đánh dấu xong, lần sau tải lại.
2. match: tiêu đề chuẩn hoá trùng khớp (hoặc giống >= 95% trong nhóm cùng 12 ký tự đầu / cuối), ID arXiv không cũ hơn
   kỳ hội nghị quá 3 năm, và có ít nhất một họ tác giả trùng (bỏ qua khi OpenReview không có tác giả). Kết quả ghi vào
   cache tra theo tiêu đề (title_lookup.jsonl, source="oai") nên known_arxiv_ids / load / corpus-refs dùng luôn.
"""
import json
import logging
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher

from common.config import RAW_DIR
from common.http import ApiClient, ApiError
from common.jsonl import append_jsonl, read_jsonl
from crawler import arxiv_ids
from crawler.parse import norm_title

log = logging.getLogger(__name__)

OAI_BASE = "https://oaipmh.arxiv.org"
OAI_DIR = RAW_DIR / "arxiv" / "oai"
_NS = {"o": "http://www.openarchives.org/OAI/2.0/", "a": "http://arxiv.org/OAI/arXiv/"}
_NEW_ID = re.compile(r"^(\d{2})(\d{2})\.\d{4,5}$")
MAX_AGE_YEARS = 3       # preprint cũ hơn kỳ hội nghị quá 3 năm: nhiều khả năng là bài khác trùng tên
BLOCK = 12              # độ dài tiền tố / hậu tố tiêu đề chuẩn hoá dùng để gom nhóm khi so gần đúng


def _months(start: str, end: date):
    y, m = map(int, start.split("-")[:2])
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _parse_page(content: bytes) -> tuple[list[dict], str | None]:
    root = ET.fromstring(content)
    err = root.find("o:error", _NS)
    if err is not None:
        if err.get("code") == "noRecordsMatch":
            return [], None
        raise ApiError(err.get("code"), err.text or "", "oai")
    rows = []
    for rec in root.iterfind("o:ListRecords/o:record", _NS):
        meta = rec.find("o:metadata/a:arXiv", _NS)
        if meta is None:        # bản ghi bị xoá
            continue
        rows.append({
            "id": meta.findtext("a:id", "", _NS),
            "title": " ".join(meta.findtext("a:title", "", _NS).split()),
            "authors": [a.findtext("a:keyname", "", _NS) for a in meta.iterfind("a:authors/a:author", _NS)],
            "categories": meta.findtext("a:categories", "", _NS),
        })
    token = root.findtext("o:ListRecords/o:resumptionToken", None, _NS)
    return rows, (token or None)


def harvest(sets=("cs",), start: str = "2022-01", end: str | None = None, interval: float = 1.0) -> None:
    client = ApiClient(OAI_BASE, min_interval=interval, max_retries=8, max_retry_after=None, timeout=300)
    today = date.today()
    for s in sets:
        for y, m in _months(start, date.fromisoformat(end + "-01") if end else today):
            path = OAI_DIR / f"{s}_{y}-{m:02d}.jsonl"
            done = path.with_suffix(".done")
            if done.exists():
                continue
            path.unlink(missing_ok=True)
            params = {"verb": "ListRecords", "metadataPrefix": "arXiv", "set": s, "from": f"{y}-{m:02d}-01"}
            if (y, m) != (today.year, today.month):     # until quá ngày hiện tại thì server báo badArgument
                until = date(y + (m == 12), m % 12 + 1, 1).toordinal() - 1
                params["until"] = date.fromordinal(until).isoformat()
            n = pages = 0
            while True:
                rows, token = _parse_page(client.request_raw("GET", "oai", params=params).content)
                append_jsonl(path, rows)
                n += len(rows)
                pages += 1
                if not token:
                    break
                params = {"verb": "ListRecords", "resumptionToken": token}
            log.info("[oai] %s %d-%02d: %d bản ghi, %d trang", s, y, m, n, pages)
            if (y, m) != (today.year, today.month):
                done.touch()


def _surname(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    parts = re.findall(r"[a-z]+", name)
    return parts[-1] if parts else ""


def _id_year(ax: str) -> int | None:
    m = _NEW_ID.match(ax)
    return 2000 + int(m.group(1)) if m else None


def _similar_to(t: str, cands) -> list[str]:
    """Các u trong cands có ratio(t, u) >= MIN_SIMILARITY. Nhóm hậu tố phổ biến ("...language models") có hàng chục
    nghìn tiêu đề, nên lọc trước theo độ dài (ratio <= 2·min/(a+b)) và quick_ratio; t là seq2 để chỉ đánh chỉ mục một lần."""
    lim = arxiv_ids.MIN_SIMILARITY
    sm = SequenceMatcher(None, autojunk=False)
    sm.set_seq2(t)
    out = []
    for u in cands:
        if u == t or 2 * min(len(t), len(u)) < lim * (len(t) + len(u)):
            continue
        sm.set_seq1(u)
        if sm.quick_ratio() >= lim and sm.ratio() >= lim:
            out.append(u)
    return out


def load_records() -> dict[str, dict]:
    """arXiv ID -> bản ghi; cùng ID ở nhiều set / tháng thì giữ bản cập nhật sau cùng."""
    recs = {}
    for path in sorted(OAI_DIR.glob("*.jsonl"), key=lambda p: p.stem.split("_")[-1]):
        for r in read_jsonl(path):
            recs[r["id"]] = r
    return recs


def _pick(sub: dict, cands: list[dict]) -> dict | None:
    """Ứng viên hợp lệ có nhiều họ tác giả trùng nhất; hoà thì lấy ID sớm nhất (bản đầu tiên)."""
    names = {_surname(a) for a in sub["authors"]} - {""}
    ok = []
    for c in cands:
        year = _id_year(c["id"])
        if year is None or year < sub["edition"] - MAX_AGE_YEARS:
            continue
        overlap = len(names & {_surname(a) for a in c["authors"]})
        if names and not overlap:
            continue
        ok.append((-overlap, c["id"], c))
    return min(ok, key=lambda x: x[:2])[2] if ok else None


def match(conn, write: bool = True) -> dict:
    """Ghép bài OpenReview với bản ghi OAI. Bài đã có arXiv ID (từ S2) dùng để đo độ chính xác, không ghi đè."""
    recs = load_records()
    by_title = defaultdict(list)
    for r in recs.values():
        by_title[norm_title(r["title"])].append(r)
    blocks = defaultdict(list)
    for t in by_title:
        if len(t) >= BLOCK:
            blocks["^" + t[:BLOCK]].append(t)
            blocks["$" + t[-BLOCK:]].append(t)
    log.info("[oai] %d bản ghi arXiv, %d tiêu đề khác nhau", len(recs), len(by_title))

    s2_known = dict(conn.execute("""SELECT o.forum_id, p.arxiv_id FROM or_submissions o
                                    JOIN papers p ON p.paper_id = o.s2_paper_id WHERE p.arxiv_id IS NOT NULL"""))
    looked = arxiv_ids.lookup_status()
    stats = defaultdict(int)
    out = []
    for forum_id, title, authors, edition in conn.execute(
            "SELECT forum_id, title, authors, edition FROM or_submissions"):
        sub = {"authors": json.loads(authors or "[]"), "edition": edition or 0}
        t = norm_title(title)
        cands, how = by_title.get(t, []), "exact"
        found = _pick(sub, cands) if cands else None
        if found is None and len(t) >= BLOCK:
            near = {u for key in ("^" + t[:BLOCK], "$" + t[-BLOCK:]) for u in blocks.get(key, ())}
            near = _similar_to(t, near)
            found, how = _pick(sub, [r for u in near for r in by_title[u]]), "fuzzy"
        known = s2_known.get(forum_id) or looked.get(forum_id, {}).get("arxiv_id")
        if known:
            stats["known"] += 1
            if found:
                stats["known_agree" if found["id"] == known else "known_disagree"] += 1
            continue
        if found is None:
            stats["not_found"] += 1
            continue
        stats[f"new_{how}"] += 1
        out.append({"forum_id": forum_id, "title": title, "arxiv_id": found["id"],
                    "matched_title": found["title"], "source": "oai", "status": "found"})
    stats["written"] = len(out)
    if write and out:
        append_jsonl(arxiv_ids.LOOKUP_PATH, out)
    log.info("[oai] %s", dict(stats))
    return dict(stats)
