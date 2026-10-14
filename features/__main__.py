"""CLI của module features (Khối 2: biểu diễn bài báo).

    python -m features items     # bảng items (gộp bài nộp lại) + versions
    python -m features quality   # điểm chất lượng q_p từ review / decision / link code
    python -m features embed     # embedding SPECTER2 (cần torch, transformers, adapters; nên có GPU)
    python -m features all       # items -> quality -> embed

Đọc data/corpus.sqlite, ghi data/features/.
"""
import argparse
import logging

from common.config import setup_logging
from common.db import connect
from features import embed, items, quality, store

log = logging.getLogger("features")


def run_items() -> None:
    conn = connect()
    it, versions = items.build_items(items.load_submissions(conn))
    conn.close()
    store.write_table(it, "items")
    store.write_table(versions, "versions")
    log.info("[items] %d submission -> %d item (%d gộp từ nhiều bản), %d là ứng viên",
             len(versions), len(it), (it.n_versions > 1).sum(), it.is_candidate.sum())


def run_quality() -> None:
    conn = connect()
    reviews = quality.load_reviews(conn)
    conn.close()
    it, versions = store.read_table("items"), store.read_table("versions")
    q = quality.compute_quality(it, versions, reviews)
    store.write_table(q, "quality")
    summary = q.merge(it[["item_id", "venue_key", "edition"]]).groupby(["venue_key", "edition"]).agg(
        n=("q", "size"), co_rating=("n_ratings", lambda s: (s > 0).mean()), q_median=("q", "median"))
    log.info("[quality] %d item\n%s", len(q), summary.round(2).to_string())


def run_embed(batch_size: int, limit: int | None) -> None:
    it = store.read_table("items")
    if limit:
        it = it.head(limit)
    emb = embed.embed_texts(it.title.tolist(), it.abstract.tolist(), batch_size=batch_size)
    embed.save(it.item_id.tolist(), emb)
    log.info("[embed] đã ghi %s %s", embed.EMB_PATH, emb.shape)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m features")
    parser.add_argument("command", choices=["items", "quality", "embed", "all"])
    parser.add_argument("--batch-size", type=int, default=32, help="embed: giảm nếu GPU hết bộ nhớ")
    parser.add_argument("--limit", type=int, help="embed: chỉ chạy N bài đầu (thử nhanh)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command in ("items", "all"):
        run_items()
    if args.command in ("quality", "all"):
        run_quality()
    if args.command in ("embed", "all"):
        run_embed(args.batch_size, args.limit)


if __name__ == "__main__":
    main()
