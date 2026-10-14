import gzip
import tempfile
import unittest
from pathlib import Path

from common.jsonl import append_jsonl, read_jsonl, write_jsonl_atomic


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


if __name__ == "__main__":
    unittest.main()
