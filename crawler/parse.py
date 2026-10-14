"""Hàm chuẩn hoá thuần (không I/O): dễ kiểm thử, dùng cho bước load."""
import re
from datetime import datetime, timezone

_DBLP_YEAR = re.compile(r"(\d{2})[a-z]?$")
_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)")


def norm_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def edition_from_dblp(dblp_key: str | None, prefix: str) -> int | None:
    """'conf/iclr/HuangCQ24' -> 2024. Trả None nếu key không thuộc venue (ví dụ bản arXiv 'journals/corr/...')."""
    if not dblp_key or not dblp_key.startswith(prefix):
        return None
    m = _DBLP_YEAR.search(dblp_key)
    return 2000 + int(m.group(1)) if m else None


def ms_to_date(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def content_value(content: dict, key: str):
    """API v2 bọc giá trị trong {"value": ...}, API v1 thì không."""
    v = content.get(key)
    return v.get("value") if isinstance(v, dict) else v


def parse_number(value) -> float | None:
    """'6: marginally above the acceptance threshold' -> 6.0; 8 -> 8.0."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = _NUMBER.match(value)
        return float(m.group(1)) if m else None
    return None


def normalize_decision(*texts: str | None) -> str | None:
    """Gộp các cách ghi decision khác nhau giữa venue / năm về một tập nhãn chung."""
    for text in texts:
        t = (text or "").lower()
        if not t:
            continue
        if "withdraw" in t:
            return "withdrawn"
        if "desk" in t and "reject" in t:
            return "desk_rejected"
        if "reject" in t:
            return "reject"
        if "oral" in t or "top-5" in t or "top 5" in t:
            return "accept_oral"
        if "spotlight" in t or "top-25" in t or "top 25" in t:
            return "accept_spotlight"
        if "poster" in t:
            return "accept_poster"
        if "accept" in t:
            return "accept"
    return None


def authors_visible(authorids) -> bool:
    """Bài đang ẩn danh có authorids rỗng hoặc chỉ là group '.../Authors'."""
    return any(isinstance(a, str) and (a.startswith("~") or "@" in a) for a in (authorids or []))


def _code_url(value) -> str | None:
    """Chỉ giữ link http(s); tác giả hay điền 'N/A', 'coming soon'..."""
    if isinstance(value, str):
        m = re.search(r"https?://\S+", value)
        return m.group(0).rstrip(".,;)") if m else None
    return None


def _reply_kind(invitation: str) -> str | None:
    if invitation.endswith("Meta_Review"):
        return "meta_review"
    if invitation.endswith(("Official_Review", "/-/Review")):
        return "review"
    if invitation.endswith("Decision"):
        return "decision"
    return None


def parse_submission(note: dict) -> tuple[dict, list[dict]]:
    """Một note submission (v1 hoặc v2) -> (dòng submission, danh sách review)."""
    c = note.get("content") or {}
    authorids = content_value(c, "authorids") or []
    reviews, decision_text, decision_date, has_meta = [], None, None, False
    for r in (note.get("details") or {}).get("directReplies") or []:
        inv = (r.get("invitations") or [r.get("invitation") or ""])[0]
        rc = r.get("content") or {}
        kind = _reply_kind(inv)
        if kind == "review":
            # ICLR/NeurIPS: rating, ICLR 2023: recommendation, ICML 2025+: overall_recommendation
            rating = next((content_value(rc, k) for k in ("rating", "recommendation", "overall_recommendation",
                                                          "overall_rating")
                           if content_value(rc, k) is not None), None)
            reviews.append({
                "review_id": r.get("id"),
                "forum_id": note["id"],
                "rating": parse_number(rating),
                "confidence": parse_number(content_value(rc, "confidence")),
                "cdate": ms_to_date(r.get("cdate")),
            })
        elif kind == "decision":
            decision_text = content_value(rc, "decision") or content_value(rc, "recommendation")
            decision_date = ms_to_date(r.get("cdate"))
        elif kind == "meta_review":
            has_meta = True

    venue_str = content_value(c, "venue")
    venueid = content_value(c, "venueid")
    visible = authors_visible(authorids)
    row = {
        "forum_id": note["id"],
        "number": note.get("number"),
        "title": content_value(c, "title"),
        "abstract": content_value(c, "abstract"),
        "tldr": content_value(c, "TLDR") or content_value(c, "TL;DR"),
        "keywords": content_value(c, "keywords") or [],
        # ICLR 2023 dùng tên trường dài, các năm sau là primary_area
        "primary_area": content_value(c, "primary_area")
                        or content_value(c, "Please_choose_the_closest_area_that_your_submission_falls_into"),
        "code_url": _code_url(content_value(c, "link_to_code") or content_value(c, "code")),
        "authors": (content_value(c, "authors") or []) if visible else [],
        "authorids": authorids if visible else [],
        "venue": venue_str,
        "venueid": venueid,
        "decision_raw": decision_text,
        "decision": normalize_decision(decision_text, venue_str, venueid),
        "decision_date": decision_date,
        "cdate": ms_to_date(note.get("cdate")),
        "odate": ms_to_date(note.get("odate")),
        "pdate": ms_to_date(note.get("pdate")),
        "has_meta_review": has_meta,
    }
    return row, reviews


# ---------------------------------------------------------------- .bbl trong source arXiv

_BIBITEM = re.compile(r"\\bibitem\s*(?:\[(?:[^\[\]]|\[[^\]]*\])*\])?\s*\{[^}]*\}")
_ACCENT_SYM = re.compile(r"\\[\"'`^~=.]\s*\{?\\?([a-zA-Z])\}?")
_ACCENT_LETTER = re.compile(r"\\[uvHcdbtrk]\{\\?([a-zA-Z])\}")
_COMMAND = re.compile(r"\\[a-zA-Z]+\*?")
_ARXIV_IN_TEXT = re.compile(r"(?<![\d.])((?:0[7-9]|[12]\d)(?:0[1-9]|1[0-2])\.\d{4,5})(?:v\d+)?(?![\d])")


def latex_to_text(s: str) -> str:
    s = _ACCENT_SYM.sub(r"\1", s)
    s = _ACCENT_LETTER.sub(r"\1", s)
    s = s.replace("\\&", "&").replace("~", " ").replace("\\\\", " ")
    s = _COMMAND.sub(" ", s)
    s = re.sub(r"[{}$]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _arxiv_id_in(raw: str) -> str | None:
    if "arxiv" not in raw.lower():
        return None
    m = _ARXIV_IN_TEXT.search(raw)
    return m.group(1) if m else None


def _biblatex_field(entry: str, name: str) -> str | None:
    key = "\\field{" + name + "}{"
    i = entry.find(key)
    if i < 0:
        return None
    start = k = i + len(key)
    depth = 1
    while k < len(entry) and depth:
        depth += {"{": 1, "}": -1}.get(entry[k], 0)
        k += 1
    return entry[start:k - 1]


def parse_bbl(text: str) -> list[dict]:
    """Tách danh sách reference từ .bbl: natbib/thebibliography (\\bibitem ... \\newblock) hoặc biblatex (\\entry)."""
    items = []
    if "\\entry{" in text:
        for entry in text.split("\\entry{")[1:]:
            entry = entry.split("\\endentry")[0]
            title = _biblatex_field(entry, "title")
            eprint = _biblatex_field(entry, "eprint") or ""
            items.append({
                "title": latex_to_text(title) if title else None,
                "arxiv_id": eprint if _ARXIV_IN_TEXT.fullmatch(eprint) else _arxiv_id_in(entry),
            })
        return items

    for raw in _BIBITEM.split(text)[1:]:
        raw = raw.split("\\end{thebibliography}")[0]
        blocks = raw.split("\\newblock")
        title = None
        if len(blocks) >= 2:
            # kiểu plainnat / icml / neurips: tác giả \newblock tiêu đề \newblock nơi đăng
            title = latex_to_text(blocks[1])
        else:
            m = re.search(r"``(.+?)''", raw, re.S)       # kiểu IEEE: ``Tiêu đề,''
            if m:
                title = latex_to_text(m.group(1))
        title = (title or "").rstrip(" .,;:") or None
        items.append({"title": title, "arxiv_id": _arxiv_id_in(raw)})
    return items
