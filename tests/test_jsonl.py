import gzip
import tempfile
import unittest
from pathlib import Path

from common import jsonl
from common.jsonl import append_jsonl, read_jsonl, repair_jsonl, write_jsonl_atomic


class TestJsonl(unittest.TestCase):
    def test_atomic_gz_is_really_gzip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl.gz"
            write_jsonl_atomic(p, [{"a": 1}, {"a": 2}])
            self.assertEqual(p.read_bytes()[:2], b"\x1f\x8b")
            self.assertEqual([r["a"] for r in read_jsonl(p)], [1, 2])

    def test_read_plain_file_with_gz_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "old.jsonl.gz"
            p.write_text('{"a": 1}\n', encoding="utf-8")
            self.assertEqual(list(read_jsonl(p)), [{"a": 1}])

    def test_append_gz(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "y.jsonl.gz"
            append_jsonl(p, [{"a": 1}])
            append_jsonl(p, [{"a": 2}])
            self.assertEqual(len(gzip.decompress(p.read_bytes()).splitlines()), 2)


class TruncatedJsonlTest(unittest.TestCase):
    """File cache phải đọc / ghi tiếp được sau khi tiến trình bị giết giữa lúc ghi."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        jsonl._repaired.clear()

    def tearDown(self):
        self.dir.cleanup()

    def _crash_midwrite(self, path: Path, n_bytes: int) -> None:
        """Mô phỏng tắt máy: ghi nối một bản ghi rồi cắt cụt n_bytes cuối."""
        append_jsonl(path, [{"id": "dở dang", "pad": "x" * 500}])
        size = path.stat().st_size
        with open(path, "r+b") as f:
            f.truncate(size - n_bytes)
        jsonl._repaired.clear()   # tiến trình mới

    def _check(self, name: str) -> None:
        path = Path(self.dir.name) / name
        append_jsonl(path, [{"id": 1}, {"id": 2}])
        append_jsonl(path, [{"id": 3}])
        for cut in (1, 7, 40):
            with self.subTest(cut=cut):
                self._crash_midwrite(path, cut)
                self.assertEqual([r["id"] for r in read_jsonl(path)][:3], [1, 2, 3])
                append_jsonl(path, [{"id": 4}])   # lần ghi đầu của tiến trình mới tự sửa file
                self.assertEqual([r["id"] for r in read_jsonl(path)], [1, 2, 3, 4])
                append_jsonl(path, [{"id": 5}])
                self.assertEqual([r["id"] for r in read_jsonl(path)], [1, 2, 3, 4, 5])
                # dọn về trạng thái 3 bản ghi cho vòng sau
                path.unlink()
                jsonl._repaired.clear()
                append_jsonl(path, [{"id": 1}, {"id": 2}])
                append_jsonl(path, [{"id": 3}])

    def test_gzip(self):
        self._check("cache.jsonl.gz")

    def test_text(self):
        self._check("cache.jsonl")

    def test_intact_file_untouched(self):
        for name in ("a.jsonl.gz", "a.jsonl"):
            path = Path(self.dir.name) / name
            append_jsonl(path, [{"id": 1}])
            append_jsonl(path, [{"id": 2}])
            self.assertEqual(repair_jsonl(path), 0)
            self.assertEqual([r["id"] for r in read_jsonl(path)], [1, 2])


if __name__ == "__main__":
    unittest.main()
