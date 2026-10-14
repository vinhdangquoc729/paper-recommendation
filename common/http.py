"""HTTP client dùng chung: giãn cách request, retry với exponential backoff."""
import logging
import random
import time

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 300  # giây; server bắt chờ lâu hơn thì coi là lỗi


class ApiError(RuntimeError):
    def __init__(self, status, body: str, url: str):
        super().__init__(f"HTTP {status} tại {url}: {body[:300]}")
        self.status = status
        self.body = body


class ApiClient:
    """Bọc requests.Session, đảm bảo cách nhau ít nhất `min_interval` giây giữa hai request."""

    def __init__(self, base_url: str, min_interval: float = 1.0, headers: dict | None = None,
                 max_retries: int = 8, timeout: float = 120):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.max_retries = max_retries
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
            except (requests.ConnectionError, requests.Timeout) as e:
                status, body, retry_after = None, str(e), None
            else:
                if resp.ok:
                    return resp
                status, body = resp.status_code, resp.text
                retry_after = resp.headers.get("Retry-After")
                if status not in RETRY_STATUS:
                    raise ApiError(status, body, url)
            if attempt == self.max_retries:
                break
            delay = min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
            if retry_after and retry_after.isdigit():
                if float(retry_after) > MAX_RETRY_AFTER:
                    # hết quota theo giờ (vd. OpenReview 500 request): báo lỗi ngay, đừng ngủ im lặng
                    raise ApiError(status, f"Retry-After={retry_after}s. {body}", url)
                delay = max(delay, float(retry_after))
            log.warning("HTTP %s, thử lại sau %.1fs (%s)", status, delay, url)
            time.sleep(delay)
        raise ApiError(status, body, url)
