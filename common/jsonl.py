"""Đọc / ghi JSONL (nén gzip nếu tên file có đuôi .gz)."""
import gzip
import json
import os
from pathlib import Path
from typing import Iterable, Iterator

_GZIP_MAGIC = b"\x1f\x8b"


def _wants_gzip(path: Path) -> bool:
    # xét cả "a.jsonl.gz.tmp" (file tạm của write_jsonl_atomic)
    return ".gz" in path.suffixes


def _open_write(path: Path, mode: str):
    if _wants_gzip(path):
        return gzip.open(path, mode + "t", encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    with open(path, "rb") as f:
        is_gzip = f.read(2) == _GZIP_MAGIC   # nhận diện theo nội dung, không tin đuôi file
    opener = gzip.open(path, "rt", encoding="utf-8") if is_gzip else open(path, "r", encoding="utf-8")
    with opener as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def append_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _open_write(path, "a") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_jsonl_atomic(path: Path, records: Iterable[dict]) -> int:
    """Ghi ra file tạm rồi đổi tên, để file cache không bao giờ bị dở dang."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    n = 0
    with _open_write(tmp, "w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    os.replace(tmp, path)
    return n
