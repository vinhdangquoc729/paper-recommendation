"""Kết nối SQLite tới corpus đã chuẩn hoá."""
import sqlite3
from pathlib import Path

from common.config import DB_PATH


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
