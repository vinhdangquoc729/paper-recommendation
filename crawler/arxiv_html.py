"""Lấy reference và từng lần trích dẫn từ bản HTML của arXiv (LaTeXML), thay cho tải cả gói source.

Bản HTML (export.arxiv.org/html/{id}) nhẹ hơn gói source hàng chục lần (không kèm hình), và LaTeXML đã tách sẵn:
- reference: <li id="bib.bibN" class="ltx_bibitem"> gồm các <span class="ltx_bibblock"> (tác giả / tiêu đề / nơi đăng);
- mỗi lần trích: <cite class="ltx_cite ..."> chứa các <a href="#bib.bibN">;
- section / subsection / phụ lục: <section class="ltx_section | ltx_subsection | ltx_appendix"> có tiêu đề <hN>.

Đầu ra cùng định dạng với latex.extract_citations (+ "refs"), khoá reference là id "bib.bibN", nên
latex.citation_features và crawler.load dùng lại nguyên vẹn. Hàm thuần, không I/O.
"""
import html as htmllib
import re

from crawler.latex import CONTEXT_CHARS
from crawler.parse import _arxiv_id_in

_SECTION_OPEN = re.compile(r'<section\b[^>]*\bclass="([^"]*)"[^>]*>')
_HEADING = re.compile(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", re.S)
_CITE = re.compile(r'<cite\b[^>]*\bclass="[^"]*\bltx_cite\b[^"]*"[^>]*>(.*?)</cite>', re.S)
_BIB_HREF = re.compile(r'href="#(bib\.bib\d+)"')
_BIBITEM = re.compile(r'<li\b[^>]*\bid="(bib\.bib\d+)"[^>]*>(.*?)</li>', re.S)
_BIBBLOCK = re.compile(r'<span\b[^>]*\bclass="ltx_bibblock"[^>]*>')
_TAG_SPAN = re.compile(r'<span\b[^>]*\bclass="ltx_tag[^"]*"[^>]*>.*?</span>', re.S)   # số thứ tự "1 ", "A.2 "
_MATH = re.compile(r"<math\b([^>]*)>.*?</math>", re.S)
_ALTTEXT = re.compile(r'\balttext="([^"]*)"')
_DROP = re.compile(r"<(script|style|svg|head)\b.*?</\1>", re.S)
_TAG = re.compile(r"<[^>]+>")
_QUOTED = re.compile(r"“(.+?)”", re.S)


def is_latexml(page: str) -> bool:
    return "ltx_document" in page or "ltx_page_main" in page


def _math_text(m: re.Match) -> str:
    alt = _ALTTEXT.search(m.group(1))
    return f" {htmllib.unescape(alt.group(1))} " if alt else " "


def _text(fragment: str) -> str:
    """HTML -> văn bản: công thức thay bằng alttext (LaTeX gốc), bỏ thẻ, giải mã thực thể, gộp khoảng trắng."""
    s = _DROP.sub(" ", fragment)
    s = _MATH.sub(_math_text, s)
    s = _TAG.sub(" ", s)
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def _title_text(heading_html: str) -> str:
    return _text(_TAG_SPAN.sub(" ", heading_html))[:120]


def _bib_span(page: str) -> tuple[int, int]:
    """Vị trí phần tài liệu tham khảo. LaTeXML đặt nó TRƯỚC phụ lục, nên không được cắt bỏ mọi thứ phía sau."""
    m = re.search(r'<section\b[^>]*\bclass="[^"]*\bltx_bibliography\b', page)
    if not m:
        return len(page), len(page)
    end = page.find("</section>", m.end())   # phần này không có section lồng bên trong
    return m.start(), (end + len("</section>") if end >= 0 else len(page))


def parse_references(page: str) -> list[dict]:
    """-> [{key, title, arxiv_id}] theo thứ tự trong danh sách tài liệu tham khảo."""
    start, end = _bib_span(page)
    refs = []
    for key, body in _BIBITEM.findall(page[start:end]):
        blocks = [_text(b) for b in _BIBBLOCK.split(body)[1:]]
        title = None
        if len(blocks) >= 2:
            title = blocks[1]                         # tác giả / tiêu đề / nơi đăng
        else:
            m = _QUOTED.search(_text(body))           # kiểu IEEE: “Tiêu đề,”
            title = m.group(1) if m else None
        title = (title or "").strip().rstrip(" .,;:") or None
        refs.append({"key": key, "title": title, "arxiv_id": _arxiv_id_in(htmllib.unescape(body))})
    return refs


def parse_html(page: str) -> dict:
    """-> {"sections", "cites": [{"keys", "sec", "sub", "appendix", "ctx"}], "refs"} như latex.extract_citations."""
    start, end = _bib_span(page)
    body = page[:start] + page[end:]   # bỏ phần tài liệu tham khảo, giữ phụ lục phía sau nó

    events = []   # (vị trí, loại, dữ liệu)
    for m in _SECTION_OPEN.finditer(body):
        classes = set(m.group(1).split())
        kind = ("appendix" if "ltx_appendix" in classes else
                "section" if "ltx_section" in classes else
                "subsection" if "ltx_subsection" in classes else None)
        if kind:
            h = _HEADING.search(body, m.end())
            events.append((m.start(), kind, _title_text(h.group(1)) if h else ""))
    cite_matches = []
    for m in _CITE.finditer(body):
        keys = list(dict.fromkeys(_BIB_HREF.findall(m.group(1))))
        if keys:   # bỏ \cite không phân giải được (ltx_missing_citation)
            cite_matches.append(m)
            events.append((m.start(), "cite", (keys, m.start())))
    events.sort(key=lambda e: e[0])

    # Như latex.py: thay mỗi <cite> bằng "\x00" rồi mới cắt ngữ cảnh, để cửa sổ ký tự không cắt ngang trích dẫn
    pieces, offsets, pos, length = [], {}, 0, 0
    for m in cite_matches:
        seg = _text(body[pos:m.start()])
        pieces.append(seg + " ")
        length += len(seg) + 1
        offsets[m.start()] = length
        pieces.append("\x00 ")
        length += 2
        pos = m.end()
    pieces.append(_text(body[pos:]))
    masked = "".join(pieces)

    sections, cites = [], []
    sec = sub = -1
    in_appendix = False
    for _, kind, data in events:
        if kind in ("section", "appendix"):
            in_appendix |= kind == "appendix"
            sections.append(data)
            sec, sub = len(sections) - 1, -1
        elif kind == "subsection":
            sections.append(data)
            sub = len(sections) - 1
        else:
            keys, s = data
            at = offsets[s]
            left = masked[max(0, at - CONTEXT_CHARS):at].replace("\x00", " [CITE] ")
            right = masked[at + 1:at + 1 + CONTEXT_CHARS].replace("\x00", " [CITE] ")
            cites.append({"keys": keys, "sec": sec, "sub": sub, "appendix": in_appendix,
                          "ctx": re.sub(r"\s+", " ", f"{left} [@] {right}").strip()})
    return {"sections": sections, "cites": cites, "refs": parse_references(page)}
