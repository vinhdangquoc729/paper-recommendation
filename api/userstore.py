"""Trạng thái người dùng: hồ sơ, bài đã xác nhận là của mình, phản hồi. Lưu ở data/app.sqlite.

Hiện chỉ có một người dùng (chưa đăng nhập); khi có đăng nhập thì thêm cột user_id.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from api.schemas import Profile
from common.config import DATA_DIR

APP_DB = DATA_DIR / "app.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile  (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS authored (paper_id TEXT PRIMARY KEY, confirmed INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS feedback (paper_id TEXT, action TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS saved    (paper_id TEXT PRIMARY KEY, ts TEXT);
"""
# phản hồi "trạng thái" (mỗi bài chỉ giữ cái mới nhất); "clicked" chỉ ghi log
STATE_ACTIONS = {"relevant", "not_relevant", "already_read"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UserStore:
    def __init__(self, path=APP_DB):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self.lock = threading.Lock()

    def get_profile(self) -> Profile:
        row = self.conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
        return Profile.model_validate_json(row[0]) if row else Profile()

    def save_profile(self, profile: Profile) -> Profile:
        with self.lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO profile (id, data) VALUES (1, ?)", (profile.model_dump_json(),))
        return profile

    def authored_status(self) -> dict[str, bool]:
        return {pid: bool(c) for pid, c in self.conn.execute("SELECT paper_id, confirmed FROM authored")}

    def set_authored(self, paper_id: str, confirmed: bool) -> None:
        with self.lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO authored VALUES (?, ?)", (paper_id, int(confirmed)))

    def add_feedback(self, paper_id: str, action: str) -> None:
        with self.lock, self.conn:
            self.conn.execute("INSERT INTO feedback VALUES (?, ?, ?)", (paper_id, action, _now()))
            if action == "saved":
                self.conn.execute("INSERT OR REPLACE INTO saved VALUES (?, ?)", (paper_id, _now()))
            elif action == "unsaved":
                self.conn.execute("DELETE FROM saved WHERE paper_id = ?", (paper_id,))

    def saved_ids(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT paper_id FROM saved ORDER BY ts DESC")]

    def latest_feedback(self) -> dict[str, str]:
        rows = self.conn.execute(
            f"SELECT paper_id, action FROM feedback WHERE action IN ({','.join('?' * len(STATE_ACTIONS))}) ORDER BY ts",
            sorted(STATE_ACTIONS))
        return dict(rows)   # bản ghi sau ghi đè bản ghi trước
