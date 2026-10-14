"""Dựng data/corpus.sqlite từ cache thô data/raw/ (chạy lại bao nhiêu lần cũng được)."""
import json
import logging
from pathlib import Path

from common.db import connect
from common.jsonl import read_jsonl
from crawler import arxiv, openreview, s2
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

    papers, refs = [], []
    for r in read_jsonl(arxiv.BBL_PATH):
        citing = by_arxiv.get(r["arxiv_id"])
        items = parse_bbl(r["bbl"]) if r["status"] == "ok" else []
        # nhiều file .bbl (bài chính + phụ lục) có thể lặp reference
        seen, unique = set(), []
        for it in items:
            tn = norm_title(it["title"])
            if tn and tn in seen:
                continue
            seen.add(tn)
            unique.append(it)
        items = unique
        papers.append({k: r[k] for k in ("arxiv_id", "status", "bytes", "seconds")}
                      | {"paper_id": citing, "has_bib": int(r["has_bib"]), "n_items": len(items)})
        for i, it in enumerate(items):
            tn = norm_title(it["title"])
            cited, how = by_arxiv.get(it["arxiv_id"]), "arxiv"
            if cited is None:
                cited, how = by_title.get(tn), "title"
            refs.append({"citing_id": citing, "idx": i, "title": it["title"], "title_norm": tn,
                         "ref_arxiv_id": it["arxiv_id"], "cited_id": cited, "match_by": how if cited else None})
    _insert(conn, "bbl_papers", papers)
    _insert(conn, "bbl_refs", refs)
    log.info("[load] arxiv bbl: %d bài, %d reference", len(papers), len(refs))


def build_db() -> None:
    conn = connect()
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    load_s2_papers(conn)
    load_s2_references(conn)
    load_s2_edges(conn)
    load_openreview(conn)
    load_arxiv_bbl(conn)
    conn.commit()
    conn.close()
