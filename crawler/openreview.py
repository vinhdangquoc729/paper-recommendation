"""Cào OpenReview (submission + review + meta-review + decision).

OpenReview hiện chặn request ẩn danh bằng "ChallengeRequiredError" (kiểm tra 10/2026), nên cần đăng nhập:
đặt OPENREVIEW_USERNAME và OPENREVIEW_PASSWORD trong file .env.

Gọi REST API trực tiếp (không dùng openreview-py) để xử lý cả API v1 lẫn v2 cùng một cách.
Cache thô: data/raw/openreview/{venue}_{edition}.jsonl.gz, mỗi dòng là một submission
kèm các reply đã lọc (chỉ giữ review / meta-review / decision).
"""
import logging
import os

from common.config import RAW_DIR
from common.http import ApiClient, ApiError
from common.jsonl import write_jsonl_atomic
from crawler.venues import OpenReviewSource

log = logging.getLogger(__name__)

OR_DIR = RAW_DIR / "openreview"
BASES = {1: "https://api.openreview.net", 2: "https://api2.openreview.net"}
KEEP_REPLY_SUFFIXES = ("Official_Review", "/-/Review", "Meta_Review", "Decision")


def raw_path(venue_key: str, edition: int):
    return OR_DIR / f"{venue_key}_{edition}.jsonl.gz"


class OpenReviewClient:
    def __init__(self, api: int):
        username = os.environ.get("OPENREVIEW_USERNAME")
        password = os.environ.get("OPENREVIEW_PASSWORD")
        if not (username and password):
            raise RuntimeError("Thiếu OPENREVIEW_USERNAME / OPENREVIEW_PASSWORD trong .env")
        self.api = ApiClient(BASES[api], min_interval=0.5)
        token = self.api.request("POST", "login", json={"id": username, "password": password})["token"]
        self.api.session.headers["Authorization"] = f"Bearer {token}"

    def iter_notes(self, page_size: int = 500, **params):
        offset = 0
        while True:
            try:
                data = self.api.request("GET", "notes", params={**params, "limit": page_size, "offset": offset})
            except ApiError as e:
                if e.status == 403 and "Challenge" in e.body:
                    raise RuntimeError("OpenReview yêu cầu challenge kể cả khi đã đăng nhập; "
                                       "thử đăng nhập trên trình duyệt rồi chạy lại") from e
                raise
            notes = data.get("notes") or []
            yield from notes
            if len(notes) < page_size:
                return
            offset += len(notes)


def _reply_invitation(reply: dict) -> str:
    return (reply.get("invitations") or [reply.get("invitation") or ""])[0]


def _slim(note: dict) -> dict:
    replies = (note.get("details") or {}).get("directReplies") or []
    note["details"] = {
        "directReplies": [r for r in replies if _reply_invitation(r).endswith(KEEP_REPLY_SUFFIXES)]
    }
    return note


def check_access() -> None:
    """Thử đăng nhập và đọc một submission ở cả API v1 lẫn v2, in kết quả dễ hiểu."""
    probes = {1: "ICLR.cc/2023/Conference/-/Blind_Submission", 2: "ICLR.cc/2024/Conference/-/Submission"}
    for api, invitation in probes.items():
        try:
            client = OpenReviewClient(api)
            note = next(client.iter_notes(page_size=1, invitation=invitation), None)
        except ApiError as e:
            print(f"[API v{api}] LỖI HTTP {e.status}: {e.body[:200]}")
        except RuntimeError as e:
            print(f"[API v{api}] LỖI: {e}")
        else:
            title = (note or {}).get("content", {}).get("title")
            title = title.get("value") if isinstance(title, dict) else title
            print(f"[API v{api}] OK, đọc được: {title!r}")


def crawl_source(venue_key: str, edition: int, src: OpenReviewSource) -> int:
    client = OpenReviewClient(src.api)
    notes = client.iter_notes(invitation=src.invitation, details="directReplies")

    def logged():
        for k, note in enumerate(notes, 1):
            if k % 1000 == 0:
                log.info("[openreview] %s %s: %d submission", venue_key, edition, k)
            yield _slim(note)

    n = write_jsonl_atomic(raw_path(venue_key, edition), logged())
    log.info("[openreview] %s %s: xong %d submission", venue_key, edition, n)
    return n
