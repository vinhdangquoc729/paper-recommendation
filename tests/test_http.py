"""ApiClient: crawler chạy nền gặp 429 (không kèm Retry-After) thì thử lại ngay, vẫn giữ giãn cách min_interval."""
import unittest
from unittest import mock

from common import http
from common.http import ApiClient


def _resp(status: int, headers: dict | None = None):
    return mock.Mock(status_code=status, ok=200 <= status < 300, text="Rate exceeded.", headers=headers or {})


class Retry429Test(unittest.TestCase):
    def _run(self, client: ApiClient, statuses: list[int], n_calls: int = 1):
        sleeps, clock = [], [0.0]

        def fake_sleep(s):
            sleeps.append(s)
            clock[0] += s

        with mock.patch.object(client.session, "request", side_effect=[_resp(s) for s in statuses]), \
             mock.patch.object(http.time, "sleep", side_effect=fake_sleep), \
             mock.patch.object(http.time, "monotonic", side_effect=lambda: clock[0]):
            for _ in range(n_calls):
                client.request_raw("GET", "x")
        return sleeps

    def test_background_crawler_retries_immediately(self):
        c = ApiClient("https://example.org", min_interval=1.0, max_retry_after=None)
        sleeps = self._run(c, [429, 429, 200])
        self.assertEqual(c.n_429, 2)
        self.assertTrue(all(s <= 1.0 for s in sleeps))     # chỉ chờ đủ min_interval, không backoff
        self.assertEqual(len(sleeps), 3)                     # trước mỗi request (đồng hồ giả bắt đầu từ 0)

    def test_long_429_streak_pauses(self):
        c = ApiClient("https://example.org", min_interval=1.0, max_retry_after=None, max_retries=30)
        sleeps = self._run(c, [429] * http.STREAK_429_PAUSE_AFTER + [200])
        self.assertIn(http.STREAK_429_PAUSE, sleeps)

    def test_interactive_client_keeps_short_backoff(self):
        c = ApiClient("https://example.org", min_interval=0.0)
        sleeps = self._run(c, [429, 200])
        self.assertEqual(len(sleeps), 1)
        self.assertLess(sleeps[0], 3)


if __name__ == "__main__":
    unittest.main()
