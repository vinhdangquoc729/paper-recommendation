"""Tải PDF từ OpenReview về cache để nhúng vào trang đọc bài.

openreview.net không cho nhúng iframe (X-Frame-Options: SAMEORIGIN) và chặn tải ẩn danh, nên backend tải hộ
qua API có đăng nhập rồi phục vụ từ cùng origin. API giới hạn khoảng 26 PDF mỗi giờ cho một tài khoản,
vì vậy PDF chỉ được tải khi người dùng yêu cầu và luôn được giữ lại trong data/pdf_cache/.

Bản demo lưu file trên ổ đĩa, chưa giới hạn dung lượng. Khi triển khai có thể thay bằng Redis / object storage
mà giữ nguyên interface is_cached() / fetch().
"""
import logging
import os
import re
import threading
import time

import requests

from common.config import DATA_DIR
from crawler.openreview import BASES, OpenReviewClient

log = logging.getLogger(__name__)

PDF_DIR = DATA_DIR / "pdf_cache"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{4,40}$")


class PdfRateLimited(Exception):
    def __init__(self, retry_after_s: int):
        super().__init__(f"Hết lượt tải PDF của OpenReview, thử lại sau khoảng {retry_after_s // 60 + 1} phút")
        self.retry_after_s = retry_after_s


class PdfUnavailable(Exception):
    pass


class PdfStore:
    def __init__(self):
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        self._client: OpenReviewClient | None = None
        self._lock = threading.Lock()
        self._blocked_until = 0.0     # khi đã biết hết quota thì khỏi gọi OpenReview cho tới lúc reset

    @staticmethod
    def path(forum_id: str):
        if not _SAFE_ID.match(forum_id):
            raise PdfUnavailable("ID không hợp lệ")
        return PDF_DIR / f"{forum_id}.pdf"

    def is_cached(self, forum_id: str) -> bool:
        return self.path(forum_id).exists()

    def fetch(self, forum_id: str):
        """Trả về đường dẫn file PDF, tải từ OpenReview nếu chưa có."""
        path = self.path(forum_id)
        if path.exists():
            return path
        with self._lock:
            if path.exists():
                return path
            wait = int(self._blocked_until - time.time())
            if wait > 0:
                raise PdfRateLimited(wait)
            resp = self._download(forum_id)
            if resp.status_code == 429:
                reset = int(resp.headers.get("ratelimit-reset") or resp.headers.get("Retry-After") or 3600)
                self._blocked_until = time.time() + reset
                raise PdfRateLimited(reset)
            if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
                raise PdfUnavailable(f"OpenReview trả về {resp.status_code}, bài này có thể không có PDF công khai")
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(resp.content)
            os.replace(tmp, path)
            log.info("pdf: đã tải %s (%d KB), còn %s lượt trong giờ", forum_id, len(resp.content) // 1024,
                     resp.headers.get("ratelimit-remaining"))
            return path

    def _download(self, forum_id: str) -> requests.Response:
        for attempt in range(2):
            if self._client is None:
                self._client = OpenReviewClient(2)
            resp = self._client.api.session.get(f"{BASES[2]}/pdf", params={"id": forum_id}, timeout=60)
            if resp.status_code in (401, 403) and attempt == 0:
                self._client = None        # token hết hạn: đăng nhập lại một lần
                continue
            return resp
        return resp
