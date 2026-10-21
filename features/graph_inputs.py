"""Đầu vào dựng recsys.snapshot.World từ data/ (đầu ra của crawler và features), ở cấp item (đã gộp bài nộp lại).

Dùng bởi eval (dựng World tại mốc T) và appdb.sync (đẩy catalog vào Postgres).
"""
import json

import numpy as np
import pandas as pd

from features import store
from features.embed import EMB_PATH, IDS_PATH
from recsys.snapshot import EDGE_FEATURES


def load_inputs(conn, with_emb: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, np.ndarray | None]:
    """-> (items: item_id, first_seen; authors: item_id, authorids, names; refs: citing_item, cited_item, EDGE_FEATURES;
    embedding theo thứ tự items hoặc None)."""
    items = store.read_table("items")[["item_id", "first_seen"]]
    versions = store.read_table("versions")[["forum_id", "item_id"]]
    f2i = versions.set_index("forum_id").item_id
    subs = pd.read_sql("SELECT forum_id, authorids, authors FROM or_submissions", conn)
    authors = pd.DataFrame({"item_id": f2i.reindex(subs.forum_id).to_numpy(),
                            "authorids": subs.authorids.map(lambda s: json.loads(s or "[]")),
                            "names": subs.authors.map(lambda s: json.loads(s or "[]"))}).dropna(subset=["item_id"])
    refs = pd.concat([
        pd.read_sql("SELECT DISTINCT citing_forum, NULL AS cited_forum FROM or_refs", conn),
        pd.read_sql(f"SELECT citing_forum, cited_forum, {', '.join(EDGE_FEATURES)} FROM or_refs "
                    "WHERE cited_forum IS NOT NULL", conn)])
    refs = refs.assign(citing_item=f2i.reindex(refs.citing_forum).to_numpy(),
                       cited_item=f2i.reindex(refs.cited_forum).to_numpy()).dropna(subset=["citing_item"])
    emb = None
    if with_emb:
        ids = IDS_PATH.read_text(encoding="utf-8").split("\n")
        row = pd.Series(np.arange(len(ids)), index=ids).reindex(items.item_id)
        if row.isna().any():
            raise RuntimeError(f"{row.isna().sum()} item chưa có embedding, chạy lại python -m features embed")
        emb = np.load(EMB_PATH, mmap_mode="r")[row.to_numpy()]
    return items, authors, refs, emb
