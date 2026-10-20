"""Dựng data/corpus.sqlite từ cache thô data/raw/ (chạy lại bao nhiêu lần cũng được)."""
import json
import logging
from pathlib import Path
from typing import Iterator

from common.db import connect
from common.jsonl import read_jsonl
from crawler import arxiv, arxiv_ids, openreview, s2
from crawler.latex import citation_features
from crawler.parse import edition_from_dblp, norm_title, parse_bbl, parse_submission
from crawler.venues import VENUES, Venue

log = logging.getLogger(__name__)

SCHEMA = Path(__file__).with_name("schema.sql")


def _paper_row(p: dict, venue: Venue) -> dict | None:
    ext = p.get("externalIds") or {}
    edition = edition_from_dblp(ext.get("DBLP"), venue.dblp_prefix) or p.get("year")
    if edition not in venue.editions:
        return None
    pub_date = p.get("publicationDate")
    return {
        "paper_id": p["paperId"],
        "corpus_id": ext.get("CorpusId"),
        "title": p.get("title"),
        "title_norm": norm_title(p.get("title")),
        "abstract": p.get("abstract"),
        "venue_key": venue.key,
        "edition": edition,
        "s2_year": p.get("year"),
        "pub_date": pub_date,
        "avail_date": pub_date or f"{edition}-{venue.default_month:02d}-01",
        "arxiv_id": ext.get("ArXiv"),
        "doi": ext.get("DOI"),
        "dblp": ext.get("DBLP"),
        "citation_count": p.get("citationCount"),
        "influential_citation_count": p.get("influentialCitationCount"),
        "reference_count": p.get("referenceCount"),
    }


def _insert(conn, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0])
    conn.executemany(
        f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [tuple(r[c] for c in cols) for r in rows],
    )


def load_s2_papers(conn) -> None:
    for venue in VENUES.values():
        papers, authors, links = [], {}, []
        for p in read_jsonl(s2.papers_path(venue.key)):
            row = _paper_row(p, venue)
            if row is None:
                continue
            papers.append(row)
            for pos, a in enumerate(p.get("authors") or []):
                if a.get("authorId"):
                    authors[a["authorId"]] = a.get("name")
                    links.append({"paper_id": row["paper_id"], "author_id": a["authorId"], "position": pos})
        _insert(conn, "papers", papers)
        _insert(conn, "authors", [{"author_id": k, "name": v} for k, v in authors.items()])
        _insert(conn, "paper_authors", links)
        log.info("[load] %s: %d bài", venue.key, len(papers))


def load_s2_references(conn) -> None:
    status, edges = {}, []
    for r in read_jsonl(s2.REFS_PATH):
        refs = r["references"]
        if not r["found"]:
            st = "not_found"
        elif refs:
            st = "ok"
        elif r.get("referenceCount"):
            st = "elided"     # S2 có đếm reference nhưng nhà xuất bản không cho trả về
        else:
            st = "empty"
        status[r["paperId"]] = (st, len(refs))
        edges.extend((r["paperId"], cited, year) for cited, year in refs)
    conn.executemany("UPDATE papers SET refs_status = ?, n_refs_returned = ? WHERE paper_id = ?",
                     [(st, n, pid) for pid, (st, n) in status.items()])
    conn.executemany("INSERT INTO citations VALUES (?, ?, ?)", edges)
    log.info("[load] references: %d bài, %d cạnh", len(status), len(edges))


def load_s2_edges(conn) -> None:
    papers, meta = [], []
    for r in read_jsonl(s2.EDGES_PATH):
        papers.append((r["paperId"], int(r["elided"]), len(r["edges"])))
        for e in r["edges"]:
            meta.append((r["paperId"], e["cited"], int(bool(e["isInfluential"])), json.dumps(e["intents"]),
                         len(e["contexts"]), json.dumps(e["contexts"], ensure_ascii=False)))
    conn.executemany("INSERT OR IGNORE INTO citation_meta_papers VALUES (?, ?, ?)", papers)
    conn.executemany("INSERT INTO citation_meta VALUES (?, ?, ?, ?, ?, ?)", meta)
    log.info("[load] edges sample: %d bài, %d cạnh", len(papers), len(meta))


def load_openreview(conn) -> None:
    title_to_s2 = {}
    for pid, venue_key, tn in conn.execute("SELECT paper_id, venue_key, title_norm FROM papers"):
        title_to_s2.setdefault((venue_key, tn), pid)

    for venue in VENUES.values():
        for edition in venue.openreview:
            path = openreview.raw_path(venue.key, edition)
            if not path.exists():
                continue
            subs, reviews = [], []
            for note in read_jsonl(path):
                row, revs = parse_submission(note)
                ed = edition or int((row["pdate"] or row["odate"] or row["cdate"] or "0")[:4])
                subs.append({
                    **row,
                    "venue_key": venue.key,
                    "edition": ed,
                    "title_norm": norm_title(row["title"]),
                    "keywords": json.dumps(row["keywords"], ensure_ascii=False),
                    "authors": json.dumps(row["authors"], ensure_ascii=False),
                    "authorids": json.dumps(row["authorids"], ensure_ascii=False),
                    "has_meta_review": int(row["has_meta_review"]),
                    "n_reviews": len(revs),
                    "s2_paper_id": title_to_s2.get((venue.key, norm_title(row["title"]))),
                })
                reviews.extend(revs)
            _insert(conn, "or_submissions", subs)
            _insert(conn, "or_reviews", reviews)
            log.info("[load] openreview %s %s: %d submission, %d review", venue.key, edition, len(subs), len(reviews))


def load_arxiv_bbl(conn, min_title_len: int = 20) -> None:
    by_arxiv, by_title = {}, {}
    for pid, ax, tn in conn.execute("SELECT paper_id, arxiv_id, title_norm FROM papers"):
        if ax:
            by_arxiv[ax] = pid
        if tn and len(tn) >= min_title_len:   # tiêu đề quá ngắn dễ khớp nhầm
            by_title.setdefault(tn, pid)

    papers, refs = [], _BatchInserter(conn, "bbl_refs")
    for _, r in _latest_bbl():
        citing = by_arxiv.get(r["arxiv_id"])
        # nhiều file .bbl (bài chính + phụ lục) có thể lặp reference
        items = _unique_refs(r) if r["status"] in REF_OK else []
        papers.append({k: r[k] for k in ("arxiv_id", "status", "bytes", "seconds")}
                      | {"paper_id": citing, "has_bib": int(r["has_bib"]), "n_items": len(items)})
        for i, it in enumerate(items):
            tn = it["title_norm"]
            cited, how = by_arxiv.get(it["arxiv_id"]), "arxiv"
            if cited is None:
                cited, how = by_title.get(tn), "title"
            refs.add({"citing_id": citing, "idx": i, "title": it["title"], "title_norm": tn,
                      "ref_arxiv_id": it["arxiv_id"], "cited_id": cited, "match_by": how if cited else None})
    _insert(conn, "bbl_papers", papers)
    refs.flush()
    log.info("[load] arxiv bbl: %d bài, %d reference", len(papers), refs.n)


def _latest_bbl() -> Iterator[tuple[str, dict]]:
    """(arxiv_id, bản ghi) theo luồng, gộp file cache chính và các file shard. Một bài có thể có nhiều bản ghi
    (lần lỗi, lần thử lại): giữ bản cùng quy tắc với arxiv.bbl_status (bản sau, trừ khi nó đè một kết quả đã xong).
    Đọc hai lượt để không phải giữ cả cache trong RAM (vài GB khi đủ 23.000 bài)."""
    chosen: dict[str, tuple[int, str]] = {}
    for i, r in enumerate(arxiv.read_bbl()):
        st = arxiv.effective_status(r)
        if arxiv.supersedes(st, chosen.get(r["arxiv_id"], (None, None))[1]):
            chosen[r["arxiv_id"]] = (i, st)
    for i, r in enumerate(arxiv.read_bbl()):
        if chosen[r["arxiv_id"]][0] == i:
            yield r["arxiv_id"], r


class _BatchInserter:
    """Ghi dần xuống SQLite thay vì gom mọi dòng vào một list (hàng triệu reference)."""

    def __init__(self, conn, table: str, size: int = 50_000):
        self.conn, self.table, self.size, self.rows, self.n = conn, table, size, [], 0

    def add(self, row: dict) -> None:
        self.rows.append(row)
        self.n += 1
        if len(self.rows) >= self.size:
            self.flush()

    def flush(self) -> None:
        _insert(self.conn, self.table, self.rows)
        self.rows = []


REF_OK = ("ok", "ok_bib", "ok_html")
CITE_FEATURES = ["n_mentions", "n_sections", "in_intro", "in_related", "in_method", "in_experiment",
                 "appendix_only", "only_in_list", "min_list_size"]


def _unique_refs(rec: dict) -> list[dict]:
    """Reference của một bản ghi cache: lấy "refs" (đã tách lúc cào, gồm cả bài chỉ có .bib), bản ghi cũ thì
    tách lại từ .bbl. Bỏ mục trùng tiêu đề (bài chính + phụ lục có thể lặp cùng reference)."""
    seen, out = set(), []
    for it in rec.get("refs") or parse_bbl(rec.get("bbl") or ""):
        tn = norm_title(it["title"])
        if tn and tn in seen:
            continue
        seen.add(tn)
        out.append(it | {"title_norm": tn})
    return out


def load_or_refs(conn, min_title_len: int = 20) -> None:
    """or_arxiv: arXiv ID của bài OpenReview. or_refs: reference của bài OpenReview, ghép về bài OpenReview."""
    rows = {f: (ax, "s2_paper") for f, ax in conn.execute(
        """SELECT o.forum_id, p.arxiv_id FROM or_submissions o
           JOIN papers p ON p.paper_id = o.s2_paper_id WHERE p.arxiv_id IS NOT NULL""")}
    for f, r in arxiv_ids.lookup_status().items():
        if r.get("arxiv_id") and f not in rows:
            rows[f] = (r["arxiv_id"], r["source"])
    _insert(conn, "or_arxiv", [{"forum_id": f, "arxiv_id": ax, "source": src} for f, (ax, src) in rows.items()])

    forum_by_arxiv = {}
    for f, (ax, _) in rows.items():
        forum_by_arxiv.setdefault(ax, f)
    forum_by_title = {}
    for f, tn in conn.execute("SELECT forum_id, title_norm FROM or_submissions"):
        if tn and len(tn) >= min_title_len:
            forum_by_title.setdefault(tn, f)

    refs = _BatchInserter(conn, "or_refs")
    citing_seen, n_in, n_feat = set(), 0, 0
    for ax, r in _latest_bbl():
        citing = forum_by_arxiv.get(ax)
        if citing is None or r["status"] not in REF_OK:
            continue
        feats = citation_features(r["cites"]) if "cites" in r else {}
        for i, it in enumerate(_unique_refs(r)):
            cited, how = forum_by_arxiv.get(it["arxiv_id"]), "arxiv"
            if cited is None and len(it["title_norm"]) >= min_title_len:
                cited, how = forum_by_title.get(it["title_norm"]), "title"
            f = feats.get(it.get("key"), {})
            refs.add({"citing_forum": citing, "idx": i, "ref_key": it.get("key"), "title": it["title"],
                      "title_norm": it["title_norm"], "ref_arxiv_id": it["arxiv_id"], "cited_forum": cited,
                      "match_by": how if cited else None, "has_cite_info": int(bool(feats)),
                      **{k: (int(f[k]) if k in f else None) for k in CITE_FEATURES}})
            citing_seen.add(citing)
            n_in += cited is not None
            n_feat += bool(f)
    refs.flush()
    n = refs.n
    log.info("[load] or_refs: %d bài có reference, %d reference, %d (%.1f%%) trỏ vào bài OpenReview, "
             "%d (%.1f%%) có đặc trưng trích dẫn từ .tex",
             len(citing_seen), n, n_in, 100 * n_in / max(n, 1), n_feat, 100 * n_feat / max(n, 1))


def build_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    load_s2_papers(conn)
    load_s2_references(conn)
    load_s2_edges(conn)
    load_openreview(conn)
    load_arxiv_bbl(conn)
    load_or_refs(conn)
    conn.commit()
    conn.close()
