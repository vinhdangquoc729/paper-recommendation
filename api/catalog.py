"""Danh mục bài báo trong bộ nhớ, nạp từ Postgres (appdb.catalog). Chỉ đọc.

Giữ bảng `df` (mỗi bài một dòng, index = paper_id) cho lọc / tìm kiếm / hiển thị, và embedding cho "bài liên quan".
Điểm review gốc đọc thẳng từ Postgres khi mở trang chi tiết.
"""
import logging

import numpy as np
import pandas as pd

from appdb.catalog import CatalogData

log = logging.getLogger(__name__)

VENUE_LABELS = {"iclr": "ICLR", "icml": "ICML", "neurips": "NeurIPS", "tmlr": "TMLR"}
DECISION_LABELS = {
    "accept_oral": "Oral", "accept_spotlight": "Spotlight", "accept_poster": "Poster", "accept": "Accept",
    "reject": "Reject", "withdrawn": "Withdrawn", "desk_rejected": "Desk reject",
}


def area_label(raw) -> str | None:
    """'deep_learning->large_language_models' (ICML) -> 'Deep learning / Large language models'."""
    if not isinstance(raw, str) or not raw:
        return None
    parts = [p.strip().replace("_", " ") for p in raw.split("->")]
    return " / ".join(p[:1].upper() + p[1:] for p in parts if p)


def _list(v) -> list:
    return v if isinstance(v, list) else []


class Catalog:
    def __init__(self, data: CatalogData, pool):
        self.version = data.version
        self.pool = pool
        df = data.papers.rename(columns={"id": "item_id", "venue": "venue_key", "author_names": "authors"})
        df["authors"] = df.authors.map(_list)
        df["keywords"] = df.keywords.map(_list)
        df["is_candidate"] = df.is_candidate.astype(int)
        oids = data.paper_authors.groupby("paper_id").openreview_id.apply(list)
        df["authorids"] = df.item_id.map(oids).map(_list)
        df["search_title"] = df.title.fillna("").str.lower()
        df["search_text"] = (df.search_title + " " + df.abstract.fillna("").str.lower() + " "
                             + df.keywords.map(lambda k: " ".join(k)).str.lower())
        self.df = df.set_index("item_id", drop=False)
        self.versions = data.versions.rename(columns={"paper_id": "item_id", "venue": "venue_key"})
        self.emb = data.emb
        self.emb_ids = df.item_id.tolist()
        self.emb_row = {pid: i for i, pid in enumerate(self.emb_ids)}
        log.info("catalog: %d bài, embedding %s", len(df), self.emb.shape)

    def get(self, paper_id: str) -> pd.Series | None:
        return self.df.loc[paper_id] if paper_id in self.df.index else None

    def raw_ratings(self, paper_id: str) -> list[float]:
        with self.pool.connection() as pg:
            rows = pg.execute("SELECT rating FROM reviews WHERE paper_id = %s AND rating IS NOT NULL",
                              (paper_id,)).fetchall()
        return [r[0] for r in rows]

    def paper_versions(self, paper_id: str) -> pd.DataFrame:
        return self.versions[self.versions.item_id == paper_id].sort_values("avail_date")

    def similar_by_embedding(self, paper_id: str, k: int) -> list[tuple[str, float]] | None:
        if paper_id not in self.emb_row:
            return None
        sims = self.emb @ self.emb[self.emb_row[paper_id]]
        top = np.argpartition(-sims, k + 1)[:k + 1]
        out = [(self.emb_ids[i], float(sims[i])) for i in top[np.argsort(-sims[top])]]
        return [(pid, s) for pid, s in out if pid != paper_id][:k]
