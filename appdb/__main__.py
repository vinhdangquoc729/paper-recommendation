"""CLI của CSDL sản phẩm.

    docker compose up -d db
    python -m appdb migrate          # tạo / cập nhật lược đồ
    python -m appdb sync             # nạp catalog từ data/ (sau crawler load + features), tạo sẵn tài khoản tác giả
    python -m appdb import-legacy    # chuyển hồ sơ / phản hồi của bản demo một người dùng (data/app.sqlite)
    python -m appdb status           # số dòng các bảng chính
"""
import argparse
import json
import logging
import sqlite3

from appdb import DATABASE_URL, connect
from appdb.migrate import migrate
from common.config import DATA_DIR, setup_logging
from common.db import connect as connect_corpus

log = logging.getLogger("appdb")

LEGACY_DB = DATA_DIR / "app.sqlite"


def import_legacy(pg) -> None:
    """Hồ sơ cũ có OpenReview ID của tác giả trong catalog thì gắn vào tài khoản tạo sẵn của tác giả đó,
    không thì tạo tài khoản mới. Phản hồi cũ chép sang events / user_papers."""
    if not LEGACY_DB.exists():
        log.info("[appdb] không có %s", LEGACY_DB)
        return
    old = sqlite3.connect(LEGACY_DB)
    row = old.execute("SELECT data FROM profile WHERE id = 1").fetchone()
    prof = json.loads(row[0]) if row else {}
    with pg.transaction():
        uid = None
        oid = (prof.get("openreview_id") or "").strip()
        if oid:
            r = pg.execute("SELECT u.id FROM users u JOIN authors a ON a.id = u.author_id WHERE a.openreview_id = %s",
                           (oid,)).fetchone()
            uid = r[0] if r else None
        if uid is None:
            uid = pg.execute("INSERT INTO users (display_name, status) VALUES (%s, 'active') RETURNING id",
                             (prof.get("display_name") or "demo",)).fetchone()[0]
        pg.execute("""UPDATE users SET status = 'active', display_name = COALESCE(NULLIF(%s, ''), display_name),
                      email = COALESCE(NULLIF(%s, ''), email), preferences = %s WHERE id = %s""",
                   (prof.get("display_name", ""), prof.get("email", ""), json.dumps(prof.get("preferences", {})), uid))
        for pid, action, ts in old.execute("SELECT paper_id, action, ts FROM feedback"):
            pg.execute("INSERT INTO events (user_id, paper_id, type, created_at) VALUES (%s, %s, %s, %s)",
                       (uid, pid, action, ts))
        for pid, ts in old.execute("SELECT paper_id, ts FROM saved"):
            pg.execute("""INSERT INTO user_papers (user_id, paper_id, role, event_time) VALUES (%s, %s, 'saved', %s)
                          ON CONFLICT DO NOTHING""", (uid, pid, ts))
        for pid, ok in old.execute("SELECT paper_id, confirmed FROM authored"):
            pg.execute("""INSERT INTO user_papers (user_id, paper_id, role, confirmed, source)
                          VALUES (%s, %s, 'authored', %s, 'app') ON CONFLICT DO NOTHING""", (uid, pid, bool(ok)))
    log.info("[appdb] đã chuyển dữ liệu demo cũ sang tài khoản id=%d", uid)


def status(pg) -> None:
    for t in ("papers", "authors", "paper_authors", "citations", "reviews", "users", "user_papers", "events",
              "rec_runs"):
        print(f"{t:15s} {pg.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>10,}")
    meta = pg.execute("SELECT version, n_papers FROM catalog_meta").fetchone()
    print("catalog_meta   ", meta)
    print("users theo status:", dict(pg.execute("SELECT status, COUNT(*) FROM users GROUP BY status").fetchall()))


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m appdb")
    parser.add_argument("command", choices=["migrate", "sync", "import-legacy", "status"])
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    log.info("[appdb] %s", DATABASE_URL.split("@")[-1])   # không in mật khẩu

    if args.command == "migrate":
        with connect(autocommit=True, vector=False) as pg:
            migrate(pg)
        return
    with connect(autocommit=True) as pg:
        if args.command == "sync":
            from appdb.sync import sync
            corpus = connect_corpus()
            sync(pg, corpus)
            corpus.close()
        elif args.command == "import-legacy":
            import_legacy(pg)
        else:
            status(pg)


if __name__ == "__main__":
    main()
