"""Nạp catalog từ Postgres vào bộ nhớ (API gọi khi khởi động và khi catalog_meta.version đổi)."""
import logging
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class CatalogData:
    version: str
    papers: pd.DataFrame          # mỗi bài một dòng, thứ tự khớp với `emb`
    emb: np.ndarray               # (n, 768) float32, SPECTER2 đã chuẩn hoá
    versions: pd.DataFrame        # forum_id, paper_id, venue, edition, decision, avail_date
    paper_authors: pd.DataFrame   # paper_id, openreview_id, name, position
    citations: pd.DataFrame       # citing_id, cited_id + đặc trưng ngữ cảnh
    with_refs: np.ndarray         # paper_id có lấy được reference


def load_catalog(pg) -> CatalogData:
    start = time.monotonic()
    version = pg.execute("SELECT version FROM catalog_meta WHERE id = 1").fetchone()
    if version is None:
        raise RuntimeError("Catalog trống: chạy python -m appdb migrate && python -m appdb sync")

    def frame(sql: str) -> pd.DataFrame:
        cur = pg.execute(sql)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])

    papers = frame("""SELECT id, venue, edition, title, abstract, tldr, keywords, primary_area, code_url, author_names,
                             decision, decision_date::text, first_seen::text, n_versions, is_candidate, n_ratings,
                             rating_z, quality, arxiv_id
                      FROM papers ORDER BY id""")
    emb = np.zeros((len(papers), 768), dtype=np.float32)
    row = {pid: i for i, pid in enumerate(papers.id)}
    with pg.cursor(binary=True) as cur:
        cur.execute("SELECT id, embedding FROM papers WHERE embedding IS NOT NULL")
        for pid, vec in cur:
            emb[row[pid]] = vec.to_numpy()
    data = CatalogData(
        version=version[0],
        papers=papers,
        emb=emb,
        versions=frame("SELECT forum_id, paper_id, venue, edition, decision, avail_date::text FROM paper_versions"),
        paper_authors=frame("""SELECT pa.paper_id, a.openreview_id, a.name, pa.position FROM paper_authors pa
                               JOIN authors a ON a.id = pa.author_id ORDER BY pa.paper_id, pa.position"""),
        citations=frame("""SELECT citing_id, cited_id, has_cite_info::int, n_mentions, in_method::int,
                                  in_experiment::int, only_in_list::int, appendix_only::int FROM citations"""),
        with_refs=np.array([r[0] for r in pg.execute("SELECT paper_id FROM papers_with_refs")]),
    )
    log.info("[catalog] %d bài, %d cạnh trích dẫn, phiên bản %s (%.0fs)", len(papers), len(data.citations),
             data.version, time.monotonic() - start)
    return data
