"""Áp các file appdb/migrations/NNN_*.sql chưa chạy, theo thứ tự tên, mỗi file trong một transaction.

Không sửa file migration đã chạy; muốn đổi lược đồ thì thêm file mới.
"""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def pending(conn) -> list[Path]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                 "(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    return [p for p in sorted(MIGRATIONS_DIR.glob("*.sql")) if p.name not in done]


def migrate(conn) -> list[str]:
    applied = []
    for path in pending(conn):
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        log.info("[appdb] đã áp %s", path.name)
        applied.append(path.name)
    if not applied:
        log.info("[appdb] lược đồ đã mới nhất")
    return applied
