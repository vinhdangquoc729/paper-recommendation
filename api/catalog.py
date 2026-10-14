"""Danh mục bài báo trong bộ nhớ: đọc đầu ra của module features (chỉ đọc)."""
import json
import logging
import sqlite3

import numpy as np
import pandas as pd

from common.config import DB_PATH, FEATURES_DB
from features import embed

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


def _json_list(s) -> list:
    try:
        v = json.loads(s) if isinstance(s, str) else []
        return v if isinstance(v, list) else []
    except json.JSONDecodeError:
        return []


class Catalog:
    def __init__(self):
        conn = sqlite3.connect(FEATURES_DB)
        df = pd.read_sql("""
            SELECT i.*, q.n_ratings, q.rating_z, q.q AS quality
            FROM items i LEFT JOIN quality q USING (item_id)""", conn)
        self.versions = pd.read_sql("SELECT * FROM versions", conn)
        conn.close()

        df["authors"] = df.authors.map(_json_list)
        df["authorids"] = df.authorids.map(_json_list)
        df["keywords"] = df.keywords.map(_json_list)
        df["n_ratings"] = df.n_ratings.fillna(0).astype(int)
        df["search_title"] = df.title.fillna("").str.lower()
        df["search_text"] = (df.search_title + " " + df.abstract.fillna("").str.lower() + " "
                             + df.keywords.map(lambda k: " ".join(k)).str.lower())
        self.df = df.set_index("item_id", drop=False)
        self.reviews_db = DB_PATH

        self.emb, self.emb_ids, self.emb_row = None, [], {}
        if embed.EMB_PATH.exists():
            ids, emb = embed.load()
            self.emb, self.emb_ids, self.emb_row = emb, ids, {pid: i for i, pid in enumerate(ids)}
            log.info("catalog: %d bài, embedding %s", len(df), emb.shape)
        else:
            log.warning("catalog: chưa có embedding, 'bài liên quan' sẽ dùng cách dự phòng")

    def get(self, paper_id: str) -> pd.Series | None:
        return self.df.loc[paper_id] if paper_id in self.df.index else None

    def raw_ratings(self, paper_id: str) -> list[float]:
        forums = self.versions.loc[self.versions.item_id == paper_id, "forum_id"].tolist()
        if not forums:
            return []
        conn = sqlite3.connect(self.reviews_db)
        rows = conn.execute(
            f"SELECT rating FROM or_reviews WHERE rating IS NOT NULL AND forum_id IN ({','.join('?' * len(forums))})",
            forums).fetchall()
        conn.close()
        return [r[0] for r in rows]

    def paper_versions(self, paper_id: str) -> pd.DataFrame:
        return self.versions[self.versions.item_id == paper_id].sort_values("avail_date")

    def similar_by_embedding(self, paper_id: str, k: int) -> list[tuple[str, float]] | None:
        if self.emb is None or paper_id not in self.emb_row:
            return None
        sims = self.emb @ self.emb[self.emb_row[paper_id]]
        top = np.argpartition(-sims, k + 1)[:k + 1]
        out = [(self.emb_ids[i], float(sims[i])) for i in top[np.argsort(-sims[top])]]
        return [(pid, s) for pid, s in out if pid != paper_id][:k]
