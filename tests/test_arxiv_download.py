"""download_resumable: kết nối đứt giữa chừng thì tải tiếp bằng Range, không tải lại từ đầu."""
import unittest
from unittest import mock

import requests

from crawler.arxiv import download_resumable

DATA = bytes(range(256)) * 100   # 25.600 byte


def _resp(status, start, cut_at=None):
    """Response giả trả DATA[start:], đứt sau khi tới byte cut_at (tính trên cả file)."""
    body = DATA[start:]
    headers = {"Content-Length": str(len(body))}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{len(DATA) - 1}/{len(DATA)}"

    def iter_content(size):
        pos = start
        while pos < len(DATA):
            if cut_at is not None and pos >= cut_at:
                raise requests.exceptions.ChunkedEncodingError("Connection broken: IncompleteRead")
            yield DATA[pos:pos + 1000]
            pos += 1000

    return mock.Mock(status_code=status, headers=headers, iter_content=iter_content, close=lambda: None)


class DownloadResumableTest(unittest.TestCase):
    def test_resumes_with_range_after_cut(self):
        client = mock.Mock()
        client.request_raw.side_effect = [_resp(200, 0, cut_at=10_000), _resp(206, 10_000, cut_at=20_000),
                                          _resp(206, 20_000)]
        self.assertEqual(download_resumable(client, "src/x"), DATA)
        ranges = [c.kwargs["headers"].get("Range") for c in client.request_raw.call_args_list]
        self.assertEqual(ranges, [None, "bytes=10000-", "bytes=20000-"])

    def test_server_ignoring_range_restarts_cleanly(self):
        client = mock.Mock()
        client.request_raw.side_effect = [_resp(200, 0, cut_at=10_000), _resp(200, 0)]
        self.assertEqual(download_resumable(client, "src/x"), DATA)

    def test_complete_download_single_request(self):
        client = mock.Mock()
        client.request_raw.side_effect = [_resp(200, 0)]
        self.assertEqual(download_resumable(client, "src/x"), DATA)
        self.assertEqual(client.request_raw.call_count, 1)


if __name__ == "__main__":
    unittest.main()
