"""Đường dẫn và biến môi trường dùng chung.

Mọi module trao đổi dữ liệu qua thư mục `data/`:
- `data/raw/`        : cache thô từ API (chỉ module crawler ghi)
- `data/corpus.sqlite`: dữ liệu đã chuẩn hoá (crawler ghi, các module khác đọc)
- `data/features/`   : biểu diễn bài báo (module features ghi)
"""
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Đọc file .env đơn giản (KEY=VALUE), không ghi đè biến đã có."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()

DATA_DIR = Path(os.environ.get("PAPERREC_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "corpus.sqlite"
FEATURES_DIR = DATA_DIR / "features"
FEATURES_DB = FEATURES_DIR / "features.sqlite"
REPORTS_DIR = ROOT / "reports"


# Console Windows mặc định cp1252, in tiếng Việt (log, --help) sẽ lỗi
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
