"""Dữ liệu người dùng trong Postgres: tài khoản, phiên đăng nhập, hồ sơ, bài đã viết / lưu / đọc, phản hồi, lịch sử gợi ý.

Mỗi tác giả trong catalog có sẵn một tài khoản `seeded` (appdb sync). "Đăng nhập với tư cách tác giả" mở tài khoản đó
(bản demo: không xác minh danh tính). Người chưa có bài thì đăng ký bằng email + mật khẩu.
"""
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from api.schemas import Preferences, Profile
from recsys.service import UserHistory

SESSION_DAYS = 30
# phản hồi "trạng thái" (mỗi bài chỉ giữ cái mới nhất, "cleared" = bỏ chọn); "clicked", "open_pdf" ghi log và, nếu
# người dùng bật tự đánh dấu đã đọc (Preferences.auto_read), thêm bài vào "đã đọc"
STATE_ACTIONS = ("interested", "not_interested", "cleared")
READ_ACTIONS = {"clicked", "open_pdf"}
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt, h = stored.split("$")
    return hmac.compare_digest(hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT).hex(), h)


class AuthError(Exception):
    pass


class UserStore:
    def __init__(self, pool):
        self.pool = pool

    # ---------- tài khoản / phiên ----------
    def _new_session(self, pg, uid: int) -> str:
        token = secrets.token_urlsafe(32)
        pg.execute("INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
                   (token, uid, datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
        pg.execute("UPDATE users SET last_login_at = now(), status = 'active' WHERE id = %s", (uid,))
        return token

    def login_as_author(self, openreview_id: str) -> str:
        with self.pool.connection() as pg:
            r = pg.execute("""SELECT u.id FROM users u JOIN authors a ON a.id = u.author_id
                              WHERE a.openreview_id = %s""", (openreview_id,)).fetchone()
            if r is None:
                raise AuthError("Không có tác giả này trong dữ liệu")
            return self._new_session(pg, r[0])

    def register(self, email: str, password: str, display_name: str) -> str:
        email = email.strip().lower()
        with self.pool.connection() as pg:
            if pg.execute("SELECT 1 FROM users WHERE email = %s", (email,)).fetchone():
                raise AuthError("Email đã được dùng")
            uid = pg.execute("""INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s)
                                RETURNING id""", (email, hash_password(password), display_name.strip())).fetchone()[0]
            return self._new_session(pg, uid)

    def login(self, email: str, password: str) -> str:
        with self.pool.connection() as pg:
            r = pg.execute("SELECT id, password_hash FROM users WHERE email = %s", (email.strip().lower(),)).fetchone()
            if r is None or not check_password(password, r[1]):
                raise AuthError("Sai email hoặc mật khẩu")
            return self._new_session(pg, r[0])

    def logout(self, token: str) -> None:
        with self.pool.connection() as pg:
            pg.execute("DELETE FROM sessions WHERE token = %s", (token,))

    def user_by_token(self, token: str | None) -> int | None:
        if not token:
            return None
        with self.pool.connection() as pg:
            r = pg.execute("SELECT user_id FROM sessions WHERE token = %s AND expires_at > now()", (token,)).fetchone()
        return r[0] if r else None

    def search_authors(self, q: str, limit: int = 20) -> list[dict]:
        """Tìm theo tên hoặc OpenReview ID, tác giả nhiều bài lên trước."""
        q = q.strip()
        if len(q) < 2:
            return []
        with self.pool.connection() as pg:
            rows = pg.execute("""
                SELECT a.openreview_id, a.name, COUNT(pa.paper_id) AS n
                FROM authors a JOIN paper_authors pa ON pa.author_id = a.id
                WHERE a.name ILIKE %(p)s OR a.openreview_id ILIKE %(p)s
                GROUP BY a.id ORDER BY n DESC, a.name LIMIT %(k)s""", {"p": f"%{q}%", "k": limit}).fetchall()
        return [{"openreview_id": o, "name": n or o, "n_papers": c} for o, n, c in rows]

    # ---------- hồ sơ ----------
    def get_profile(self, uid: int) -> Profile:
        with self.pool.connection() as pg:
            r = pg.execute("""SELECT u.display_name, COALESCE(u.email, ''), COALESCE(a.openreview_id, ''), u.preferences
                              FROM users u LEFT JOIN authors a ON a.id = u.author_id WHERE u.id = %s""",
                           (uid,)).fetchone()
        return Profile(display_name=r[0], email=r[1], openreview_id=r[2],
                       preferences=Preferences.model_validate(r[3] or {}))

    def save_profile(self, uid: int, profile: Profile) -> Profile:
        """OpenReview ID không đổi ở đây: danh tính gắn với tài khoản tác giả (đăng nhập với tư cách tác giả)."""
        email = profile.email.strip().lower() or None
        with self.pool.connection() as pg:
            if email and pg.execute("SELECT 1 FROM users WHERE email = %s AND id <> %s", (email, uid)).fetchone():
                raise AuthError("Email đã được dùng")
            pg.execute("UPDATE users SET display_name = %s, email = %s, preferences = %s WHERE id = %s",
                       (profile.display_name.strip(), email, Jsonb(profile.preferences.model_dump()), uid))
        return self.get_profile(uid)

    def openreview_id(self, uid: int) -> str | None:
        with self.pool.connection() as pg:
            r = pg.execute("SELECT a.openreview_id FROM users u JOIN authors a ON a.id = u.author_id WHERE u.id = %s",
                           (uid,)).fetchone()
        return r[0] if r else None

    # ---------- bài đã viết / lưu / đọc, phản hồi ----------
    def authored_status(self, uid: int) -> dict[str, bool]:
        with self.pool.connection() as pg:
            return dict(pg.execute("SELECT paper_id, confirmed FROM user_papers WHERE user_id = %s AND role = 'authored'",
                                   (uid,)).fetchall())

    def set_authored(self, uid: int, paper_id: str, confirmed: bool) -> None:
        with self.pool.connection() as pg:
            pg.execute("""INSERT INTO user_papers (user_id, paper_id, role, confirmed) VALUES (%s, %s, 'authored', %s)
                          ON CONFLICT (user_id, paper_id, role) DO UPDATE SET confirmed = EXCLUDED.confirmed,
                          event_time = now()""", (uid, paper_id, confirmed))

    def add_event(self, uid: int, paper_id: str, action: str, context: dict | None = None) -> None:
        with self.pool.connection() as pg, pg.transaction():
            pg.execute("INSERT INTO events (user_id, paper_id, type, context) VALUES (%s, %s, %s, %s)",
                       (uid, paper_id, action, Jsonb(context or {})))
            if action == "saved":
                pg.execute("""INSERT INTO user_papers (user_id, paper_id, role) VALUES (%s, %s, 'saved')
                              ON CONFLICT (user_id, paper_id, role) DO UPDATE SET event_time = now()""",
                           (uid, paper_id))
            elif action == "unsaved":
                pg.execute("DELETE FROM user_papers WHERE user_id = %s AND paper_id = %s AND role = 'saved'",
                           (uid, paper_id))
            elif action in READ_ACTIONS and self._auto_read(pg, uid):
                pg.execute("""INSERT INTO user_papers (user_id, paper_id, role) VALUES (%s, %s, 'read')
                              ON CONFLICT (user_id, paper_id, role) DO UPDATE SET event_time = now()""",
                           (uid, paper_id))

    @staticmethod
    def _auto_read(pg, uid: int) -> bool:
        r = pg.execute("SELECT preferences FROM users WHERE id = %s", (uid,)).fetchone()
        return Preferences.model_validate((r and r[0]) or {}).auto_read

    def saved_ids(self, uid: int) -> list[str]:
        with self.pool.connection() as pg:
            return [r[0] for r in pg.execute("""SELECT paper_id FROM user_papers WHERE user_id = %s AND role = 'saved'
                                                ORDER BY event_time DESC""", (uid,))]

    def _latest_feedback(self, pg, uid: int) -> dict[str, tuple[str, datetime]]:
        rows = pg.execute("""SELECT DISTINCT ON (paper_id) paper_id, type, created_at FROM events
                             WHERE user_id = %s AND type = ANY(%s) ORDER BY paper_id, created_at DESC""",
                          (uid, list(STATE_ACTIONS))).fetchall()
        return {p: (a, t) for p, a, t in rows if a != "cleared"}

    def latest_feedback(self, uid: int) -> dict[str, str]:
        with self.pool.connection() as pg:
            return {p: a for p, (a, _) in self._latest_feedback(pg, uid).items()}

    def history(self, uid: int) -> UserHistory:
        """Tất cả những gì bộ gợi ý cần về người dùng, trong một kết nối."""
        h = UserHistory(openreview_id=self.openreview_id(uid))
        with self.pool.connection() as pg:
            for pid, role, ok, when in pg.execute(
                    "SELECT paper_id, role, confirmed, event_time FROM user_papers WHERE user_id = %s", (uid,)):
                if role == "authored":
                    (h.manual_authored if ok else h.not_mine).add(pid)
                elif role == "saved":
                    h.saved[pid] = when
                elif role == "read":
                    h.read[pid] = when
            for pid, (action, when) in self._latest_feedback(pg, uid).items():
                if action == "interested":
                    h.interested[pid] = when
                else:
                    h.not_interested.add(pid)
        h.hidden = h.not_interested | set(h.read)
        return h

    def log_recommendations(self, uid: int, mode: str, model: str, catalog_version: str, recs) -> int:
        with self.pool.connection() as pg, pg.transaction():
            run = pg.execute("""INSERT INTO rec_runs (user_id, mode, model, catalog_version) VALUES (%s, %s, %s, %s)
                                RETURNING id""", (uid, mode, model, catalog_version)).fetchone()[0]
            with pg.cursor().copy("COPY rec_items (run_id, rank, paper_id, score, score_parts) FROM STDIN") as cp:
                for rank, r in enumerate(recs):
                    cp.write_row([run, rank, r.paper_id, r.score, json.dumps(r.parts)])
        return run
