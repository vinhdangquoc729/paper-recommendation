"""CSDL của sản phẩm: Postgres + pgvector (docker compose up -d db).

- catalog (papers, authors, citations, ...): chỉ `python -m appdb sync` ghi, từ đầu ra của crawler / features;
- người dùng (users, user_papers, events, rec_runs, ...): API ghi.
Chuỗi kết nối: biến môi trường DATABASE_URL (mặc định là DB trong docker-compose.yml, cổng 55432).
"""
import os

import psycopg

import common.config  # noqa: F401  (đọc .env)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://paperrec:paperrec@localhost:55432/paperrec")


def connect(autocommit: bool = False, vector: bool = True) -> psycopg.Connection:
    conn = psycopg.connect(DATABASE_URL, autocommit=autocommit)
    if vector:
        from pgvector.psycopg import register_vector
        register_vector(conn)
    return conn
