"""Lấy reference từ source LaTeX trên arXiv (file .bbl), bù cho các bài S2 ẩn reference.

Tải https://export.arxiv.org/e-print/{id} (không cần tài khoản), đọc gói tar trong bộ nhớ,
chỉ giữ lại nội dung .bbl. Điều khoản API arXiv: tối đa 1 request / 3 giây, 1 kết nối.
Cache: data/raw/arxiv/bbl.jsonl.gz (resume theo arxiv_id).
"""
import gzip
import io
import logging
import tarfile
import time

from common.config import RAW_DIR
from common.http import ApiClient, ApiError
from common.jsonl import append_jsonl, read_jsonl

log = logging.getLogger(__name__)

ARXIV_BASE = "https://export.arxiv.org"
BBL_PATH = RAW_DIR / "arxiv" / "bbl.jsonl.gz"


def _bibliography_part(tex: str) -> str:
    i = tex.find("\\begin{thebibliography}")
    return tex[i:] if i >= 0 else tex


def extract_bbl(content: bytes) -> tuple[str, str, bool]:
    """Gói e-print -> (status, nội dung bibliography, có file .bib không).

    status: ok / no_bbl / pdf_only / unknown_format
    """
    if content[:4] == b"%PDF":
        return "pdf_only", "", False
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as tar:
            files = [m for m in tar.getmembers() if m.isfile()]
            has_bib = any(m.name.lower().endswith(".bib") for m in files)
            texts = [tar.extractfile(m).read().decode("utf-8", "replace")
                     for m in files if m.name.lower().endswith(".bbl")]
            if not texts:   # bibliography viết thẳng trong .tex
                for m in files:
                    if m.name.lower().endswith(".tex"):
                        tex = tar.extractfile(m).read().decode("utf-8", "replace")
                        if "\\bibitem" in tex:
                            texts.append(_bibliography_part(tex))
            return ("ok" if texts else "no_bbl"), "\n".join(texts), has_bib
    except tarfile.TarError:
        pass
    try:   # bài chỉ có một file .tex, nén gzip
        tex = gzip.decompress(content).decode("utf-8", "replace")
    except (OSError, EOFError):
        return "unknown_format", "", False
    if "\\bibitem" in tex:
        return "ok", _bibliography_part(tex), False
    return "no_bbl", "", False


def crawl_bbl(arxiv_ids: list[str], min_interval: float = 3.0) -> int:
    done = {r["arxiv_id"] for r in read_jsonl(BBL_PATH)}
    todo = [a for a in dict.fromkeys(arxiv_ids) if a not in done]
    log.info("[arxiv] đã có %d, cần tải %d (giãn cách %.1fs)", len(done), len(todo), min_interval)
    client = ApiClient(ARXIV_BASE, min_interval=min_interval, max_retries=5)
    t_start = time.monotonic()
    for k, aid in enumerate(todo, 1):
        t0 = time.monotonic()
        try:
            resp = client.request_raw("GET", f"e-print/{aid}")
            status, bbl, has_bib = extract_bbl(resp.content)
            size = len(resp.content)
        except ApiError as e:
            status, bbl, has_bib, size = f"http_{e.status}", "", False, 0
        append_jsonl(BBL_PATH, [{
            "arxiv_id": aid, "status": status, "bytes": size,
            "seconds": round(time.monotonic() - t0, 2), "has_bib": has_bib, "bbl": bbl,
        }])
        if k % 20 == 0 or k == len(todo):
            rate = (time.monotonic() - t_start) / k
            log.info("[arxiv] %d / %d (%.1f s/bài, còn ~%.1f giờ)", k, len(todo), rate, rate * (len(todo) - k) / 3600)
    return len(todo)
