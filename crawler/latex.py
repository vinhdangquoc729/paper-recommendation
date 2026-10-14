"""Đọc source LaTeX để lấy đặc trưng của từng lần trích dẫn (spec mục 5.2, thay cho GROBID).

Từ các file .tex: gộp \\input / \\include bắt đầu từ file chính, bỏ comment, rồi đi tuần tự qua phần thân
bài để ghi lại mỗi lệnh \\cite: các khoá, section đang đứng, có nằm trong phụ lục không, và đoạn văn quanh nó.
Hàm thuần, không I/O.
"""
import re

from crawler.parse import latex_to_text

_COMMENT = re.compile(r"(?<!\\)%.*")
_INPUT = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}")
# \cite, \citep, \citet*, \citealp, \parencite, \textcite, \autocite... (không lấy \nocite)
_CITE = re.compile(r"\\(?!nocite\b)[A-Za-z]*cite[A-Za-z]*\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")
_SECTION = re.compile(r"\\(section|subsection)\*?\s*(?:\[[^\]]*\])?\s*\{")
_APPENDIX = re.compile(r"\\appendix\b|\\begin\{appendices\}")
CONTEXT_CHARS = 220
MAX_INPUT_DEPTH = 6


def _strip_comments(tex: str) -> str:
    return "\n".join(_COMMENT.sub("", line) for line in tex.split("\n"))


def _norm_path(name: str) -> str:
    name = name.strip().replace("\\", "/").lstrip("./")
    return name[:-4] if name.lower().endswith(".tex") else name


def flatten_tex(files: dict[str, str]) -> str:
    """{đường dẫn: nội dung .tex} -> một văn bản duy nhất, đã thay \\input bằng nội dung file và bỏ comment."""
    if not files:
        return ""
    by_name = {_norm_path(k): _strip_comments(v) for k, v in files.items()}
    mains = [k for k, v in by_name.items() if "\\documentclass" in v and "\\begin{document}" in v]
    # nhiều file chính (bài + phụ lục riêng): lấy file dài nhất
    main = max(mains or by_name, key=lambda k: len(by_name[k]))

    def expand(text: str, depth: int, seen: set) -> str:
        def repl(m):
            target = _norm_path(m.group(1))
            hit = by_name.get(target) or next((v for k, v in by_name.items() if k.endswith("/" + target)), None)
            if hit is None or target in seen or depth >= MAX_INPUT_DEPTH:
                return ""
            return expand(hit, depth + 1, seen | {target})
        return _INPUT.sub(repl, text)

    return expand(by_name[main], 0, {main})


def _braced(text: str, start: int) -> tuple[str, int]:
    """Đọc nội dung trong ngoặc nhọn bắt đầu ngay sau `start` (đã qua dấu '{'), cho phép lồng nhau."""
    depth, k = 1, start
    while k < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[k], 0)
        k += 1
    return text[start:k - 1], k


def extract_citations(tex: str) -> dict:
    """-> {"sections": [tiêu đề section], "cites": [{"keys", "sec", "sub", "appendix", "ctx"}]}

    sec / sub: chỉ số trong "sections" của section / subsection đang đứng (-1 nếu chưa có).
    ctx: đoạn văn quanh lệnh \\cite, lệnh đang xét thay bằng [@], các \\cite khác thay bằng [CITE].
    """
    begin = tex.find("\\begin{document}")
    body = tex[begin:] if begin >= 0 else tex
    end = body.find("\\end{document}")
    body = body[:end] if end >= 0 else body

    events = []   # (vị trí, loại, dữ liệu)
    for m in _SECTION.finditer(body):
        title, _ = _braced(body, m.end())
        events.append((m.start(), m.group(1), latex_to_text(title)[:120]))
    for m in _APPENDIX.finditer(body):
        events.append((m.start(), "appendix", None))
    for m in _CITE.finditer(body):
        keys = [k.strip() for k in m.group(1).split(",") if k.strip()]
        if keys:
            events.append((m.start(), "cite", (keys, m.start(), m.end())))
    events.sort(key=lambda e: e[0])

    # Thay mọi \cite bằng dấu "\x00" trước khi cắt ngữ cảnh, để cửa sổ ký tự không cắt ngang một lệnh \cite
    # (nếu cắt ngang thì khoá thô như "Luo2023WizardCoderEC" lọt vào ngữ cảnh).
    masked, offsets, pos, length = [], {}, 0, 0
    for m in _CITE.finditer(body):
        masked.append(body[pos:m.start()])
        length += m.start() - pos
        offsets[m.start()] = length
        masked.append("\x00")
        length += 1
        pos = m.end()
    masked.append(body[pos:])
    masked = "".join(masked)

    sections, cites = [], []
    sec = sub = -1
    in_appendix = False
    for _, kind, data in events:
        if kind == "section":
            sections.append(data)
            sec, sub = len(sections) - 1, -1
        elif kind == "subsection":
            sections.append(data)
            sub = len(sections) - 1
        elif kind == "appendix":
            in_appendix = True
        else:
            keys, s, _ = data
            at = offsets[s]
            left = masked[max(0, at - CONTEXT_CHARS):at].replace("\x00", " [CITE] ")
            right = masked[at + 1:at + 1 + CONTEXT_CHARS].replace("\x00", " [CITE] ")
            cites.append({"keys": keys, "sec": sec, "sub": sub, "appendix": in_appendix,
                          "ctx": latex_to_text(left + " [@] " + right)})
    return {"sections": sections, "cites": cites}


# Phân loại section theo tiêu đề (tiếng Anh, viết thường); thứ tự kiểm tra quan trọng
SECTION_KINDS = [
    ("related", re.compile(r"related|background|prior work|preliminar|literature")),
    ("intro", re.compile(r"introduction|motivation|overview")),
    ("experiment", re.compile(r"experiment|evaluation|result|ablation|benchmark|empirical|analysis|setup")),
    ("method", re.compile(r"method|approach|model|framework|algorithm|proposed|architecture|our |formulation")),
]
LIST_CITE_MIN_KEYS = 4    # \cite{a,b,c,d} trở lên coi là "trích hàng loạt"


def section_kind(title: str | None) -> str:
    t = (title or "").lower()
    return next((kind for kind, rx in SECTION_KINDS if rx.search(t)), "other")


def citation_features(cites: dict) -> dict[str, dict]:
    """{"sections", "cites"} của một bài -> đặc trưng theo từng khoá reference (spec mục 5.2):
    n_mentions, n_sections, in_intro / in_related / in_method / in_experiment, appendix_only,
    only_in_list (mọi lần nhắc đều nằm trong \\cite có >= 4 khoá), min_list_size."""
    sections = cites.get("sections") or []
    feats: dict[str, dict] = {}
    for c in cites.get("cites") or []:
        # dùng section cấp 1; subsection chỉ giúp khi section cấp 1 không rõ loại
        kinds = {section_kind(sections[c["sec"]]) if c["sec"] >= 0 else "front"}
        if c.get("sub", -1) >= 0:
            kinds.add(section_kind(sections[c["sub"]]))
        for key in c["keys"]:
            f = feats.setdefault(key, {"n_mentions": 0, "secs": set(), "kinds": set(), "appendix_only": True,
                                       "only_in_list": True, "min_list_size": 10 ** 6})
            f["n_mentions"] += 1
            f["secs"].add(c["sec"])
            f["kinds"] |= kinds
            f["appendix_only"] &= bool(c["appendix"])
            f["only_in_list"] &= len(c["keys"]) >= LIST_CITE_MIN_KEYS
            f["min_list_size"] = min(f["min_list_size"], len(c["keys"]))
    return {key: {"n_mentions": f["n_mentions"], "n_sections": len(f["secs"]),
                  "in_intro": "intro" in f["kinds"], "in_related": "related" in f["kinds"],
                  "in_method": "method" in f["kinds"], "in_experiment": "experiment" in f["kinds"],
                  "appendix_only": f["appendix_only"], "only_in_list": f["only_in_list"],
                  "min_list_size": f["min_list_size"]}
            for key, f in feats.items()}
