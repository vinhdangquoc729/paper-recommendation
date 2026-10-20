"""HTTP client dùng chung: giãn cách request, retry với exponential backoff."""
import logging
import random
import time

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 300  # giây; mặc định: server bắt chờ lâu hơn thì báo lỗi (hợp với API phục vụ giao diện)
# Crawler chạy nền (max_retry_after=None) gặp 429 không kèm Retry-After (arXiv): thử lại ngay, chỉ chờ đủ
# min_interval như mọi request. Đo ngày 2026-10-15: 429 "Rate exceeded." của arXiv là do máy chủ gốc quá tải, xảy ra
# ngẫu nhiên khoảng 45% request kể cả request đầu tiên sau vài phút nghỉ, nên chờ lâu không giúp gì.
# Chốt an toàn: 429 liên tiếp STREAK_429_PAUSE_AFTER lần thì có thể đã bị chặn thật, nghỉ STREAK_429_PAUSE giây.
STREAK_429_PAUSE_AFTER = 20
STREAK_429_PAUSE = 60.0


class ApiError(RuntimeError):
    def __init__(self, status, body: str, url: str):
        super().__init__(f"HTTP {status} tại {url}: {body[:300]}")
        self.status = status
        self.body = body


class ApiClient:
    """Bọc requests.Session, đảm bảo cách nhau ít nhất `min_interval` giây giữa hai request."""

    def __init__(self, base_url: str, min_interval: float = 1.0, headers: dict | None = None,
                 max_retries: int = 8, timeout: float = 120, max_retry_after: float | None = MAX_RETRY_AFTER):
        """max_retry_after=None: luôn chờ theo Retry-After của server dù lâu bao nhiêu (dùng cho crawler chạy nền)."""
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.n_429 = 0          # tổng số 429 (để crawler báo trong dòng tiến độ)
        self._streak_429 = 0    # số 429 liên tiếp
        self.max_retry_after = max_retry_after
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "paper-recsys-student-project/0.1"
        if headers:
            self.session.headers.update(headers)
        self._last = 0.0

    def request(self, method: str, path: str, **kwargs):
        """Gọi API trả JSON."""
        return self.request_raw(method, path, **kwargs).json()

    def request_raw(self, method: str, path: str, **kwargs) -> requests.Response:
        """Gọi và trả nguyên Response (dùng khi tải file nhị phân)."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        status, body, retry_after = None, "", None
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
                # ChunkedEncodingError: kết nối đứt giữa lúc tải body (hay gặp với file vài chục MB)
                status, body, retry_after = None, str(e), None
            else:
                if resp.ok:
                    self._streak_429 = 0
                    return resp
                status, body = resp.status_code, resp.text
                retry_after = resp.headers.get("Retry-After")
                if status not in RETRY_STATUS:
                    raise ApiError(status, body, url)
            if status == 429:
                self.n_429 += 1
                self._streak_429 += 1
            if attempt == self.max_retries:
                break
            delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
            if retry_after and retry_after.isdigit():
                if self.max_retry_after is not None and float(retry_after) > self.max_retry_after:
                    # hết quota theo giờ (vd. OpenReview 500 request): báo lỗi ngay, đừng ngủ im lặng
                    raise ApiError(status, f"Retry-After={retry_after}s. {body}", url)
                delay = max(delay, float(retry_after))
            elif status == 429 and self.max_retry_after is None:
                if self._streak_429 >= STREAK_429_PAUSE_AFTER:
                    log.warning("%d lần 429 liên tiếp, nghỉ %.0fs (%s)", self._streak_429, STREAK_429_PAUSE, url)
                    self._streak_429 = 0
                    time.sleep(STREAK_429_PAUSE)
                else:
                    log.debug("HTTP 429 %r, thử lại ngay (%s)", body.strip()[:60], url)
                continue   # vòng sau vẫn chờ đủ min_interval
            log.warning("HTTP %s %r, thử lại sau %.1fs (%s)", status, body.strip()[:60], delay, url)
            time.sleep(delay)
        raise ApiError(status, body, url)
