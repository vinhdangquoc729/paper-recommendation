"""Nạp catalog từ data/ (crawler + features) vào Postgres và tạo sẵn tài khoản cho mọi tác giả.

Bảng catalog được thay cả lô trong MỘT transaction (API đang chạy vẫn đọc bản cũ đến khi commit):
papers, paper_versions, paper_authors, citations, papers_with_refs, reviews. Riêng `authors` chỉ thêm / cập nhật tên,
không xoá, vì `users` trỏ tới. Sau đó:
- tạo tài khoản `seeded` cho tác giả chưa có tài khoản;
- ánh xạ lại paper_id trong dữ liệu người dùng nếu bài được gộp khác đi (qua paper_versions);
- ghi catalog_meta.version để API biết mà nạp lại.
"""
import json
import logging
import math
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from features import store
from features.graph_inputs import load_inputs
from recsys.snapshot import EDGE_FEATURES, build_world

log = logging.getLogger(__name__)

CATALOG_TABLES = ("reviews", "papers_with_refs", "citations", "paper_authors", "paper_versions", "papers")


def _v(x):
    """Giá trị pandas / numpy -> kiểu Python cho COPY (NaN -> None)."""
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(x) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, str):
        return x.replace("\x00", "")   # vài abstract có ký tự NUL, Postgres không nhận trong cột TEXT
    return x


def _copy(cur, table: str, cols: list[str], rows) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row([_v(x) for x in r])
            n += 1
    return n


def _paper_rows(items: pd.DataFrame, quality: pd.DataFrame, arxiv: pd.Series):
    it = items.merge(quality[["item_id", "n_ratings", "rating_z", "q"]], on="item_id", how="left")
    for r in it.itertuples(index=False):
        yield (r.item_id, r.venue_key, r.edition, r.title or "", r.abstract, r.tldr, r.keywords or "[]",
               r.primary_area, r.code_url, r.authors or "[]", r.decision, r.decision_date, r.first_seen,
               r.n_versions, bool(r.is_candidate), 0 if pd.isna(r.n_ratings) else int(r.n_ratings), r.rating_z, r.q,
               arxiv.get(r.item_id))


PAPER_COLS = ["id", "venue", "edition", "title", "abstract", "tldr", "keywords", "primary_area", "code_url",
              "author_names", "decision", "decision_date", "first_seen", "n_versions", "is_candidate", "n_ratings",
              "rating_z", "quality", "arxiv_id"]


def sync(pg, corpus) -> dict:
    """pg: kết nối Postgres (appdb.connect), corpus: kết nối data/corpus.sqlite."""
    start = time.monotonic()
    items = store.read_table("items")
    quality = store.read_table("quality")
    versions = store.read_table("versions")
    _, authors, refs, emb = load_inputs(corpus, with_emb=True)
    if len(emb) != len(items):
        raise RuntimeError("embedding không khớp số item, chạy lại python -m features embed")
    f2i = versions.set_index("forum_id").item_id
    or_arxiv = pd.read_sql("SELECT forum_id, arxiv_id FROM or_arxiv", corpus)
    arxiv = (or_arxiv.assign(item_id=f2i.reindex(or_arxiv.forum_id).to_numpy()).dropna()
             .drop_duplicates("item_id").set_index("item_id").arxiv_id)
    reviews = pd.read_sql("SELECT forum_id, rating, confidence FROM or_reviews", corpus)
    reviews["paper_id"] = f2i.reindex(reviews.forum_id).to_numpy()
    reviews = reviews.dropna(subset=["paper_id"])

    # Tác giả của bài: bản nộp có danh sách dài nhất (như recsys.snapshot); chỉ giữ OpenReview ID (~...)
    best: dict[str, tuple[list, list]] = {}
    for item, ids, names in zip(authors.item_id, authors.authorids, authors.names):
        if len(ids) > len(best.get(item, ([], []))[0]):
            best[item] = (ids, names)
    author_name: dict[str, str] = {}
    pa_rows = []
    for item, (ids, names) in best.items():
        for pos, oid in enumerate(ids):
            if isinstance(oid, str) and oid.startswith("~"):
                pa_rows.append((item, oid, pos))
                if pos < len(names) and names[pos]:
                    author_name.setdefault(oid, names[pos])

    world = build_world("9999-01-01", items[["item_id", "first_seen"]], authors, refs)
    ids = world.item_ids
    e = world.edges
    cit_rows = ((ids[a], ids[b], bool(info > 0), int(n), bool(m > 0), bool(x > 0), bool(li > 0), bool(ap > 0))
                for a, b, info, n, m, x, li, ap in zip(e.a, e.b, *(e[c].fillna(0) for c in EDGE_FEATURES)))

    stats = {}
    with pg.transaction():
        cur = pg.cursor()
        cur.execute(f"TRUNCATE {', '.join(CATALOG_TABLES)}")
        # Nạp metadata và embedding vào bảng tạm rồi chèn một lần (UPDATE embedding sau sẽ nhân đôi dung lượng bảng)
        cur.execute("CREATE TEMP TABLE papers_tmp (LIKE papers) ON COMMIT DROP")
        stats["papers"] = _copy(cur, "papers_tmp", PAPER_COLS, _paper_rows(items, quality, arxiv))
        cur.execute("CREATE TEMP TABLE emb_tmp (id TEXT, embedding vector(768)) ON COMMIT DROP")
        with cur.copy("COPY emb_tmp (id, embedding) FROM STDIN WITH (FORMAT BINARY)") as cp:
            cp.set_types(["text", "vector"])
            for pid, vec in zip(items.item_id, emb):
                cp.write_row([pid, np.asarray(vec, dtype=np.float32)])
        cols = ", ".join(PAPER_COLS)
        cur.execute(f"""INSERT INTO papers ({cols}, embedding)
                        SELECT {', '.join('p.' + c for c in PAPER_COLS)}, e.embedding
                        FROM papers_tmp p LEFT JOIN emb_tmp e USING (id)""")

        stats["versions"] = _copy(cur, "paper_versions", ["forum_id", "paper_id", "venue", "edition", "decision",
                                                          "avail_date"],
                                  versions[["forum_id", "item_id", "venue_key", "edition", "decision",
                                            "avail_date"]].itertuples(index=False))

        cur.execute("CREATE TEMP TABLE authors_tmp (openreview_id TEXT, name TEXT) ON COMMIT DROP")
        _copy(cur, "authors_tmp", ["openreview_id", "name"],
              ((oid, author_name.get(oid)) for oid in sorted({r[1] for r in pa_rows})))
        cur.execute("""INSERT INTO authors (openreview_id, name) SELECT openreview_id, name FROM authors_tmp
                       ON CONFLICT (openreview_id) DO UPDATE SET name = COALESCE(EXCLUDED.name, authors.name)""")
        cur.execute("CREATE TEMP TABLE pa_tmp (paper_id TEXT, openreview_id TEXT, position INT) ON COMMIT DROP")
        _copy(cur, "pa_tmp", ["paper_id", "openreview_id", "position"], pa_rows)
        cur.execute("""INSERT INTO paper_authors (paper_id, author_id, position)
                       SELECT t.paper_id, a.id, MIN(t.position) FROM pa_tmp t JOIN authors a USING (openreview_id)
                       GROUP BY t.paper_id, a.id""")
        stats["paper_authors"] = cur.rowcount

        stats["citations"] = _copy(cur, "citations", ["citing_id", "cited_id", "has_cite_info", "n_mentions",
                                                      "in_method", "in_experiment", "only_in_list", "appendix_only"],
                                   cit_rows)
        stats["papers_with_refs"] = _copy(cur, "papers_with_refs", ["paper_id"],
                                          ((p,) for p in ids[world.has_refs]))
        stats["reviews"] = _copy(cur, "reviews", ["forum_id", "paper_id", "rating", "confidence"],
                                 reviews[["forum_id", "paper_id", "rating", "confidence"]].itertuples(index=False))

        # Dữ liệu người dùng trỏ tới bài đã đổi đại diện (gộp khác đi): ánh xạ lại qua mọi lần nộp
        cur.execute("""INSERT INTO user_papers (user_id, paper_id, role, confirmed, source, event_time)
                       SELECT up.user_id, v.paper_id, up.role, up.confirmed, up.source, up.event_time
                       FROM user_papers up JOIN paper_versions v ON v.forum_id = up.paper_id
                       WHERE v.paper_id <> up.paper_id ON CONFLICT DO NOTHING""")
        cur.execute("""DELETE FROM user_papers up USING paper_versions v
                       WHERE v.forum_id = up.paper_id AND v.paper_id <> up.paper_id""")
        cur.execute("""UPDATE events e SET paper_id = v.paper_id FROM paper_versions v
                       WHERE e.paper_id = v.forum_id AND v.paper_id <> e.paper_id""")

        cur.execute("""INSERT INTO users (author_id, display_name, status)
                       SELECT a.id, COALESCE(a.name, ''), 'seeded' FROM authors a
                       WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.author_id = a.id)""")
        stats["new_seeded_users"] = cur.rowcount
        version = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur.execute("""INSERT INTO catalog_meta (id, version, synced_at, n_papers) VALUES (1, %s, now(), %s)
                       ON CONFLICT (id) DO UPDATE SET version = EXCLUDED.version, synced_at = EXCLUDED.synced_at,
                       n_papers = EXCLUDED.n_papers""", (version, stats["papers"]))
    stats["seconds"] = round(time.monotonic() - start)
    log.info("[appdb] sync xong: %s", json.dumps(stats))
    return stats
