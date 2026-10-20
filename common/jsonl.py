"""Đọc / ghi JSONL (nén gzip nếu tên file có đuôi .gz).

File cache được ghi nối từng bản ghi một, nên nếu tiến trình bị giết giữa lúc ghi (tắt máy, hết pin)
thì chỉ có phần đuôi bị cụt. Lần ghi nối đầu tiên của mỗi tiến trình cắt bỏ phần đuôi đó
(`repair_jsonl`), còn `read_jsonl` bỏ qua đuôi hỏng thay vì báo lỗi.
"""
import gzip
import json
import logging
import os
import zlib
from pathlib import Path
from typing import Iterable, Iterator

log = logging.getLogger(__name__)

_GZIP_MAGIC = b"\x1f\x8b"
_CHUNK = 1 << 20
_repaired: set[Path] = set()


def _wants_gzip(path: Path) -> bool:
    # xét cả "a.jsonl.gz.tmp" (file tạm của write_jsonl_atomic)
    return ".gz" in path.suffixes


def _is_gzip(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(2) == _GZIP_MAGIC   # nhận diện theo nội dung, không tin đuôi file


def _open_write(path: Path, mode: str):
    if _wants_gzip(path):
        return gzip.open(path, mode + "t", encoding="utf-8")
    return open(path, mode, encoding="utf-8")


def _complete(text: bytes) -> bool:
    """Đoạn văn bản kết thúc bằng xuống dòng và dòng cuối là JSON hợp lệ."""
    if not text.endswith(b"\n"):
        return False
    last = text.rstrip(b"\n").rsplit(b"\n", 1)[-1]
    if not last.strip():
        return True
    try:
        json.loads(last)
        return True
    except ValueError:
        return False


def _gzip_valid_prefix(path: Path) -> int:
    """Số byte đầu file gồm toàn các gzip member trọn vẹn (mỗi lần ghi nối tạo một member)."""
    good = pos = 0                   # good: cuối member trọn vẹn gần nhất; pos: vị trí đầu `data`
    d, text = zlib.decompressobj(31), b""
    with open(path, "rb") as f:
        while chunk := f.read(_CHUNK):
            data = chunk
            while data:
                try:
                    text += d.decompress(data)
                except zlib.error:
                    return good
                if not d.eof:
                    pos += len(data)
                    break
                pos += len(data) - len(d.unused_data)
                if not _complete(text):
                    return good
                good = pos
                data, d, text = d.unused_data, zlib.decompressobj(31), b""
    return good


def _text_valid_prefix(path: Path) -> int:
    with open(path, "rb") as f:
        content = f.read()
    end = len(content)
    while end and not _complete(content[:end]):
        end = content.rfind(b"\n", 0, end - 1) + 1   # lùi về cuối dòng trước đó
    return end


def repair_jsonl(path: Path) -> int:
    """Cắt bỏ phần đuôi dở dang của file; trả về số byte đã cắt."""
    if not path.exists() or path.stat().st_size == 0:
        return 0
    size = path.stat().st_size
    keep = _gzip_valid_prefix(path) if _is_gzip(path) else _text_valid_prefix(path)
    if keep < size:
        with open(path, "r+b") as f:
            f.truncate(keep)
        log.warning("%s: cắt %d byte cuối bị ghi dở (tiến trình trước bị ngắt giữa lúc ghi)", path, size - keep)
    return size - keep


def read_jsonl(path: Path) -> Iterator[dict]:
    if not path.exists():
        return
    opener = gzip.open(path, "rt", encoding="utf-8") if _is_gzip(path) else open(path, "r", encoding="utf-8")
    with opener as f:
        try:
            for line in f:
                if line.strip():
                    yield json.loads(line)
        except (EOFError, gzip.BadGzipFile, zlib.error, json.JSONDecodeError) as e:
            log.warning("%s: bỏ qua phần đuôi hỏng (%s); lần ghi tiếp theo sẽ tự sửa", path, e)


def append_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    key = path.resolve()
    if key not in _repaired:   # chỉ quét một lần cho mỗi file trong một tiến trình
        repair_jsonl(path)
        _repaired.add(key)
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
