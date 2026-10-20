"""Chạy crawler song song (--shard i/n): chia bài không trùng, đọc gộp các file cache, khoá file khi ghi."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import jsonl
from common.jsonl import append_jsonl
from crawler import arxiv
from crawler.load import _latest_bbl


class ShardTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        jsonl._repaired.clear()
        self.patch = mock.patch.object(arxiv, "BBL_PATH", Path(self.dir.name) / "bbl.jsonl.gz")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dir.cleanup()

    def test_shards_partition_ids(self):
        ids = [f"25{m:02d}.{k:05d}" for m in range(1, 13) for k in range(0, 300, 7)]
        owners = [[i for i in range(3) if arxiv.in_shard(a, (i, 3))] for a in ids]
        self.assertTrue(all(len(o) == 1 for o in owners))                 # mỗi bài đúng một phần
        sizes = [sum(o == [i] for o in owners) for i in range(3)]
        self.assertGreater(min(sizes), len(ids) / 3 * 0.8)                # chia tương đối đều

    def test_status_merges_files_without_downgrading(self):
        ok = {"status": "ok_html", "cites": {"sections": [], "cites": []}, "refs": []}
        append_jsonl(arxiv.BBL_PATH, [{"arxiv_id": "A", "status": "error_X"}, {"arxiv_id": "B", **ok}])
        append_jsonl(arxiv.shard_path(0), [{"arxiv_id": "A", **ok}])
        append_jsonl(arxiv.shard_path(1), [{"arxiv_id": "B", "status": "http_503"}, {"arxiv_id": "C", "status": "http_503"}])
        self.assertEqual(arxiv.bbl_status(), {"A": "ok_html", "B": "ok_html", "C": "http_503"})
        latest = {a: r["status"] for a, r in _latest_bbl()}
        self.assertEqual(latest, {"A": "ok_html", "B": "ok_html", "C": "http_503"})

    def test_lock_blocks_second_writer(self):
        with arxiv.exclusive(arxiv.shard_path(0)):
            with self.assertRaises(RuntimeError):
                with arxiv.exclusive(arxiv.shard_path(0)):
                    pass
            with arxiv.exclusive(arxiv.shard_path(1)):   # phần khác thì được
                pass
        with arxiv.exclusive(arxiv.shard_path(0)):       # nhả khoá rồi thì lấy lại được
            pass


if __name__ == "__main__":
    unittest.main()
