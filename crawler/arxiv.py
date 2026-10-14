"""Lấy reference từ source LaTeX trên arXiv: danh sách reference (.bbl) và từng lần trích dẫn (\\cite trong .tex).

Tải https://export.arxiv.org/e-print/{id} (không cần tài khoản), đọc gói tar trong bộ nhớ, giữ lại
nội dung .bbl và các lần \\cite (khoá, section, đoạn văn quanh nó) chứ không giữ cả file .tex.
Điều khoản API arXiv: tối đa 1 request / 3 giây, 1 kết nối.
Cache: data/raw/arxiv/bbl.jsonl.gz (resume theo arxiv_id; bản ghi chưa có "cites" sẽ được tải lại).
"""
import gzip
import io
import logging
import tarfile
import time

from common.config import RAW_DIR
from common.http import ApiClient, ApiError
from common.jsonl import append_jsonl, read_jsonl
from crawler.latex import extract_citations, flatten_tex
from crawler.parse import parse_bbl, parse_bib

log = logging.getLogger(__name__)

ARXIV_BASE = "https://export.arxiv.org"
BBL_PATH = RAW_DIR / "arxiv" / "bbl.jsonl.gz"


def _bibliography_part(tex: str) -> str:
    i = tex.find("\\begin{thebibliography}")
    return tex[i:] if i >= 0 else tex


def extract_source(content: bytes) -> dict:
    """Gói e-print -> {status, bbl, has_bib, tex, bib}. tex / bib: {đường dẫn: nội dung}.

    status: ok / no_bbl / pdf_only / unknown_format
    """
    if content[:4] == b"%PDF":
        return {"status": "pdf_only", "bbl": "", "has_bib": False, "tex": {}, "bib": {}}
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
            files = [m for m in tar.getmembers() if m.isfile()]
            has_bib = any(m.name.lower().endswith(".bib") for m in files)
            read = lambda m: tar.extractfile(m).read().decode("utf-8", "replace")   # noqa: E731
            tex = {m.name: read(m) for m in files if m.name.lower().endswith(".tex")}
            bib = {m.name: read(m) for m in files if m.name.lower().endswith(".bib")}
            texts = [read(m) for m in files if m.name.lower().endswith(".bbl")]
            if not texts:   # bibliography viết thẳng trong .tex
                texts = [_bibliography_part(t) for t in tex.values() if "\\bibitem" in t]
            return {"status": "ok" if texts else "no_bbl", "bbl": "\n".join(texts), "has_bib": has_bib, "tex": tex, "bib": bib}
    except tarfile.TarError:
        pass
    try:   # bài chỉ có một file .tex, nén gzip
        tex = gzip.decompress(content).decode("utf-8", "replace")
    except (OSError, EOFError):
        return {"status": "unknown_format", "bbl": "", "has_bib": False, "tex": {}, "bib": {}}
    ok = "\\bibitem" in tex
    return {"status": "ok" if ok else "no_bbl", "bbl": _bibliography_part(tex) if ok else "",
            "has_bib": False, "tex": {"main.tex": tex}, "bib": {}}


def extract_bbl(content: bytes) -> tuple[str, str, bool]:
    src = extract_source(content)
    return src["status"], src["bbl"], src["has_bib"]


# Kết quả "cuối cùng": có rồi thì không tải lại. Các trạng thái khác (5xx, mất mạng...) được thử lại.
# ok: có .bbl; ok_bib: không có .bbl nhưng có .bib (bài mới hay chỉ nộp .bib)
FINAL_STATUSES = {"ok", "ok_bib", "no_bbl", "pdf_only", "unknown_format", "http_403", "http_404", "http_410"}


def bbl_status() -> dict[str, str]:
    """arxiv_id -> trạng thái mới nhất trong cache (bản ghi sau ghi đè bản ghi trước).

    Bản ghi ok / no_bbl cũ chưa có thông tin \\cite (cào trước khi có latex.py và trước khi đọc .bib)
    được coi là chưa xong ("stale") để tải lại.
    """
    return {r["arxiv_id"]: (r["status"] if "cites" in r or r["status"] not in ("ok", "no_bbl") else "stale")
            for r in read_jsonl(BBL_PATH)}


def _references(src: dict, cites: dict) -> list[dict]:
    """Danh sách reference {key, title, arxiv_id}: từ .bbl nếu có, nếu không thì các mục .bib được \\cite
    (file .bib thường chứa cả nghìn mục không dùng, chỉ giữ mục có trích, theo thứ tự trích lần đầu)."""
    if src["bbl"]:
        return parse_bbl(src["bbl"])
    entries = {}
    for text in src["bib"].values():
        for e in parse_bib(text):
            entries.setdefault(e["key"], e)
    cited = dict.fromkeys(k for c in cites["cites"] for k in c["keys"])
    return [entries[k] for k in cited if k in entries]


def crawl_bbl(arxiv_ids: list[str], min_interval: float = 3.0, max_passes: int = 3) -> int:
    """Tải .bbl cho các arxiv_id chưa có kết quả cuối cùng.

    Không bao giờ dừng giữa chừng vì lỗi: 429/503 thì chờ theo Retry-After rồi thử lại, lỗi tạm thời
    được ghi lại và thử lại ở vòng sau (tối đa max_passes vòng), lần chạy sau cũng thử lại.
    """
    client = ApiClient(ARXIV_BASE, min_interval=min_interval, max_retries=8, max_retry_after=None)
    total = 0
    for attempt in range(1, max_passes + 1):
        status = bbl_status()
        todo = [a for a in dict.fromkeys(arxiv_ids) if status.get(a) not in FINAL_STATUSES]
        if not todo:
            break
        log.info("[arxiv] vòng %d: cần tải %d bài (giãn cách %.1fs)", attempt, len(todo), min_interval)
        t_start, failed = time.monotonic(), 0
        for k, aid in enumerate(todo, 1):
            t0 = time.monotonic()
            st, bbl, has_bib, size, cites, refs = "", "", False, 0, None, None
            try:
                resp = client.request_raw("GET", f"e-print/{aid}")
                size = len(resp.content)
                src = extract_source(resp.content)
                st, bbl, has_bib = src["status"], src["bbl"], src["has_bib"]
                cites = extract_citations(flatten_tex(src["tex"])) if src["tex"] else {"sections": [], "cites": []}
                refs = _references(src, cites)
                if st == "no_bbl" and refs:
                    st = "ok_bib"
            except ApiError as e:
                st = f"http_{e.status}"
            except Exception as e:   # lỗi bất ngờ (giải nén, đọc tar, regex...): ghi lại rồi đi tiếp
                st = f"error_{type(e).__name__}"
            failed += st not in FINAL_STATUSES
            rec = {"arxiv_id": aid, "status": st, "bytes": size, "seconds": round(time.monotonic() - t0, 2),
                   "has_bib": has_bib, "bbl": bbl}
            if cites is not None:
                rec["cites"] = cites
                rec["refs"] = refs
            append_jsonl(BBL_PATH, [rec])
            if k % 20 == 0 or k == len(todo):
                rate = (time.monotonic() - t_start) / k
                log.info("[arxiv] %d / %d (%.1f s/bài, còn ~%.1f giờ, lỗi tạm thời %d)",
                         k, len(todo), rate, rate * (len(todo) - k) / 3600, failed)
        total += len(todo)
        if failed:
            log.info("[arxiv] %d bài lỗi tạm thời, nghỉ 60s rồi thử lại", failed)
            time.sleep(60)
    return total
