"""Lấy reference từ arXiv: danh sách reference và từng lần trích dẫn (khoá, section, đoạn văn quanh nó).

1. Thử bản HTML https://export.arxiv.org/html/{id} trước (LaTeXML, xem arxiv_html.py): nhẹ hơn gói source hàng chục
   lần vì không kèm hình. Kiểm tra trên 4 bài: khớp tuyệt đối với cách đọc source, trừ trích dẫn nằm trong hình
   TikZ (cây phân loại của bài survey) mà LaTeXML không chuyển được.
2. Không có HTML thì tải gói source https://export.arxiv.org/src/{id}, đọc tar trong bộ nhớ, giữ lại .bbl
   (hoặc .bib) và các lần \\cite trong .tex, không giữ cả file.
Giãn cách: quy định "1 request / 3 giây" trong Terms of Use chỉ áp dụng cho các API (query, OAI-PMH, RSS); với tải
hàng loạt từ export.arxiv.org, trang bulk data coi "4 request/giây, nghỉ 1 giây mỗi đợt" là hợp lý. Ở đây mỗi
tiến trình giãn cách SRC_MIN_INTERVAL (đổi bằng --src-interval), có thể chạy nhiều tiến trình với --shard; 429 thì
thử lại ngay, 20 lần 429 liên tiếp thì nghỉ 60 giây (xem common/http.py). Không dùng /e-print/{id}: đường dẫn này
chuyển hướng 301 sang /src/{id}, mỗi bài thành hai request liền nhau.
Cache: data/raw/arxiv/bbl.jsonl.gz và bbl_shard{i}.jsonl.gz (resume theo arxiv_id; bản ghi chưa có "cites" sẽ
được tải lại).
"""
import gzip
import io
import logging
import os
import tarfile
import time
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import requests

from common.config import RAW_DIR
from common.http import ApiClient, ApiError
from common.jsonl import append_jsonl, read_jsonl
from crawler.arxiv_html import is_latexml, parse_html
from crawler.latex import extract_citations, flatten_tex
from crawler.parse import parse_bbl, parse_bib

log = logging.getLogger(__name__)

ARXIV_BASE = "https://export.arxiv.org"
BBL_PATH = RAW_DIR / "arxiv" / "bbl.jsonl.gz"
SRC_MIN_INTERVAL = 0.1


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
# ok_html: lấy từ bản HTML; ok: có .bbl; ok_bib: không có .bbl nhưng có .bib (bài mới hay chỉ nộp .bib)
FINAL_STATUSES = {"ok_html", "ok", "ok_bib", "no_bbl", "pdf_only", "unknown_format",
                  "http_403", "http_404", "http_410"}


# Chạy song song (--shard i/n): mỗi tiến trình chỉ tải bài thuộc phần của mình và ghi vào file cache riêng;
# mọi chỗ đọc cache đọc gộp file chính + các file shard. Mỗi tiến trình dùng giãn cách min_interval riêng.
SHARD_GLOB = "bbl_shard*.jsonl.gz"


def shard_path(i: int) -> Path:
    return BBL_PATH.with_name(f"bbl_shard{i}.jsonl.gz")


def bbl_paths() -> list[Path]:
    return [BBL_PATH] + sorted(BBL_PATH.parent.glob(SHARD_GLOB))


def read_bbl() -> Iterator[dict]:
    """Mọi bản ghi cache, file chính trước rồi tới các file shard."""
    for path in bbl_paths():
        yield from read_jsonl(path)


def in_shard(aid: str, shard: tuple[int, int]) -> bool:
    """Chia bài cố định theo crc32 (không dùng hash() vì Python đổi seed giữa các tiến trình)."""
    i, n = shard
    return zlib.crc32(aid.encode()) % n == i


def effective_status(r: dict) -> str:
    """Bản ghi ok / no_bbl cũ chưa có thông tin \\cite (cào trước khi có latex.py và trước khi đọc .bib)
    được coi là chưa xong ("stale") để tải lại."""
    return r["status"] if "cites" in r or r["status"] not in ("ok", "no_bbl") else "stale"


def supersedes(new_status: str, old_status: str | None) -> bool:
    """Bản ghi sau thay bản ghi trước, trừ khi bản trước đã xong còn bản sau thì chưa (các file shard được đọc
    lần lượt chứ không theo thời gian, nên không được để một lần lỗi ở file sau đè kết quả tốt ở file trước)."""
    return old_status is None or new_status in FINAL_STATUSES or old_status not in FINAL_STATUSES


def bbl_status() -> dict[str, str]:
    """arxiv_id -> trạng thái hiện tại trong cache (gộp mọi file)."""
    status: dict[str, str] = {}
    for r in read_bbl():
        st = effective_status(r)
        if supersedes(st, status.get(r["arxiv_id"])):
            status[r["arxiv_id"]] = st
    return status


@contextmanager
def exclusive(path: Path):
    """Khoá file cache cho riêng tiến trình này (hai tiến trình cùng ghi nối một file .gz sẽ làm hỏng nó).
    Khoá tự nhả khi tiến trình kết thúc, kể cả khi bị giết."""
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path.with_name(path.name + ".lock"), "a+")
    try:
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise RuntimeError(f"{path.name} đang được một tiến trình crawler khác ghi. Muốn chạy song song thì "
                           f"mỗi tiến trình dùng một --shard i/n khác nhau (cùng n).") from None
    try:
        yield
    finally:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.close()


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


def fetch_html(client: ApiClient, aid: str) -> dict | None:
    """Bản HTML (LaTeXML) đã parse, kèm "bytes"; None nếu bài không có HTML hoặc HTML không có reference."""
    try:
        resp = client.request_raw("GET", f"html/{aid}")
    except ApiError as e:
        if e.status in (403, 404, 410):
            return None
        raise
    page = resp.content.decode("utf-8", "replace")
    if not is_latexml(page):
        return None
    parsed = parse_html(page)
    return parsed | {"bytes": len(resp.content)} if parsed["refs"] else None


_BODY_ERRORS = (requests.exceptions.ChunkedEncodingError, requests.ConnectionError, requests.Timeout)
MAX_RESUMES = 100   # file vài chục MB có lúc bị cắt ở từng mốc 1 MiB


def download_resumable(client: ApiClient, path: str) -> bytes:
    """Tải file, đứt giữa chừng thì xin tiếp phần còn lại bằng header Range.

    Khi quá tải, arXiv hay cắt kết nối đúng ở mốc 5 MiB (5242880 byte) với file lớn hơn, lần nào cũng vậy,
    nên tải lại từ đầu không bao giờ xong; tải tiếp từ chỗ đứt thì được.
    """
    buf, total = bytearray(), None
    for _ in range(MAX_RESUMES):
        headers = {"Range": f"bytes={len(buf)}-"} if buf else {}
        resp = client.request_raw("GET", path, headers=headers, stream=True)
        try:
            if buf and resp.status_code != 206:   # server bỏ qua Range: nhận lại cả file từ đầu
                buf.clear()
            if total is None:
                cr = resp.headers.get("Content-Range", "")
                cl = resp.headers.get("Content-Length")
                total = int(cr.rsplit("/", 1)[1]) if "/" in cr and not cr.endswith("*") else \
                    (int(cl) if cl and resp.status_code == 200 else None)
            try:
                for chunk in resp.iter_content(1 << 16):
                    buf += chunk
            except _BODY_ERRORS as e:
                log.info("[arxiv] %s: đứt sau %d / %s byte, tải tiếp phần còn lại (%s)",
                         path, len(buf), total, type(e).__name__)
                continue
        finally:
            resp.close()
        if total is None or len(buf) >= total:
            return bytes(buf)
    raise requests.exceptions.ChunkedEncodingError(f"{path}: chưa tải xong sau {MAX_RESUMES} lần ({len(buf)} byte)")


def crawl_bbl(arxiv_ids: list[str], min_interval: float = SRC_MIN_INTERVAL, max_passes: int = 3,
              shard: tuple[int, int] | None = None) -> int:
    """Tải reference cho các arxiv_id chưa có kết quả cuối cùng.

    Không bao giờ dừng giữa chừng vì lỗi: 429 thì thử lại ngay, 503 thì chờ rồi thử lại, lỗi tạm thời
    được ghi lại và thử lại ở vòng sau (tối đa max_passes vòng), lần chạy sau cũng thử lại.
    shard=(i, n): chỉ tải phần thứ i trong n phần, ghi vào file cache riêng (chạy n tiến trình song song).
    """
    out, tag = BBL_PATH, "[arxiv]"
    if shard is not None:
        arxiv_ids = [a for a in arxiv_ids if in_shard(a, shard)]
        out, tag = shard_path(shard[0]), f"[arxiv {shard[0]}/{shard[1]}]"
    with exclusive(out):
        return _crawl(arxiv_ids, min_interval, max_passes, out, tag)


def _crawl(arxiv_ids: list[str], min_interval: float, max_passes: int, out: Path, tag: str) -> int:
    client = ApiClient(ARXIV_BASE, min_interval=min_interval, max_retries=15, max_retry_after=None)
    total = 0
    for attempt in range(1, max_passes + 1):
        status = bbl_status()
        todo = [a for a in dict.fromkeys(arxiv_ids) if status.get(a) not in FINAL_STATUSES]
        if not todo:
            break
        log.info("%s vòng %d: cần tải %d bài (giãn cách %.2fs)", tag, attempt, len(todo), min_interval)
        t_start, failed = time.monotonic(), 0
        for k, aid in enumerate(todo, 1):
            t0 = time.monotonic()
            st, bbl, has_bib, size, cites, refs, origin = "", "", False, 0, None, None, None
            try:
                html = fetch_html(client, aid)
                if html is not None:
                    st, size, refs, origin = "ok_html", html["bytes"], html["refs"], "html"
                    cites = {"sections": html["sections"], "cites": html["cites"]}
                else:   # không có bản HTML: tải cả gói source
                    content = download_resumable(client, f"src/{aid}")
                    size, origin = len(content), "src"
                    src = extract_source(content)
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
            rec = {"arxiv_id": aid, "status": st, "source": origin, "bytes": size,
                   "seconds": round(time.monotonic() - t0, 2), "has_bib": has_bib, "bbl": bbl}
            if cites is not None:
                rec["cites"] = cites
                rec["refs"] = refs
            append_jsonl(out, [rec])
            if k % 20 == 0 or k == len(todo):
                rate = (time.monotonic() - t_start) / k
                log.info("%s %d / %d (%.1f s/bài, còn ~%.1f giờ, lỗi tạm thời %d, đã gặp %d lần 429)",
                         tag, k, len(todo), rate, rate * (len(todo) - k) / 3600, failed, client.n_429)
        total += len(todo)
        if failed:
            log.info("%s %d bài lỗi tạm thời, nghỉ 60s rồi thử lại", tag, failed)
            time.sleep(60)
    return total
