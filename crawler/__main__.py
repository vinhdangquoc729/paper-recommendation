"""CLI của module crawler.

    python -m crawler s2-papers               # metadata bài theo venue (vài phút)
    python -m crawler s2-refs                 # reference của mọi bài (lâu nhất)
    python -m crawler s2-edges --sample 300   # intents / isInfluential / contexts cho mẫu bài
    python -m crawler openreview-check        # thử đăng nhập + đọc 1 submission, không cào gì
    python -m crawler openreview              # cần OPENREVIEW_USERNAME / PASSWORD trong .env
    python -m crawler arxiv-refs --limit 100 --validate 30
                                              # reference từ .bbl trên arXiv cho bài S2 ẩn
                                              # (+ một mẫu bài S2 có refs để kiểm tra parser)
    python -m crawler load                    # dựng data/corpus.sqlite từ data/raw/
    python -m crawler all                     # s2-papers -> s2-refs -> s2-edges -> load

Mọi bước đều có cache trong data/raw/, chạy lại chỉ lấy phần còn thiếu.
"""
import argparse
import logging
import random

from common.config import setup_logging
from common.jsonl import read_jsonl
from crawler import arxiv, openreview, s2
from crawler.load import _paper_row, build_db
from crawler.venues import VENUES

log = logging.getLogger("crawler")


def corpus_paper_ids(venue_keys) -> list[str]:
    ids = []
    for key in venue_keys:
        venue = VENUES[key]
        ids += [p["paperId"] for p in read_jsonl(s2.papers_path(key)) if _paper_row(p, venue)]
    return ids


def ids_with_refs() -> list[str]:
    return [r["paperId"] for r in read_jsonl(s2.REFS_PATH) if r["references"]]


def arxiv_targets(venue_keys, limit: int | None, validate: int, seed: int) -> list[str]:
    """arXiv ID của bài bị S2 ẩn reference (xáo trộn), cộng `validate` bài S2 có refs để đối chiếu."""
    has_refs = {r["paperId"]: bool(r["references"]) for r in read_jsonl(s2.REFS_PATH)}
    elided, ok = [], []
    for key in venue_keys:
        for p in read_jsonl(s2.papers_path(key)):
            ax = (p.get("externalIds") or {}).get("ArXiv")
            if ax and _paper_row(p, VENUES[key]) and p["paperId"] in has_refs:
                (ok if has_refs[p["paperId"]] else elided).append(ax)
    rng = random.Random(seed)
    rng.shuffle(elided)
    rng.shuffle(ok)
    log.info("arxiv-refs: %d bài bị ẩn có arXiv ID", len(elided))
    return ok[:validate] + elided[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m crawler")
    parser.add_argument("command", choices=["s2-papers", "s2-refs", "s2-edges", "openreview", "openreview-check",
                                            "arxiv-refs", "load", "all"])
    parser.add_argument("--venues", nargs="+", default=list(VENUES), choices=list(VENUES))
    parser.add_argument("--editions", nargs="+", type=int, help="chỉ cho lệnh openreview")
    parser.add_argument("--skip-existing", action="store_true", help="openreview: bỏ qua nguồn đã có cache")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--sample", type=int, default=300, help="số bài cho s2-edges")
    parser.add_argument("--limit", type=int, help="arxiv-refs: số bài bị ẩn tối đa (mặc định: tất cả)")
    parser.add_argument("--validate", type=int, default=0, help="arxiv-refs: số bài S2 có refs để kiểm tra parser")
    parser.add_argument("--interval", type=float, default=3.0, help="arxiv-refs: giây giữa hai request")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    cmd = args.command
    if cmd in ("s2-papers", "all"):
        client = s2.make_client()
        for key in args.venues:
            n = s2.crawl_venue_papers(client, VENUES[key])
            log.info("s2-papers %s: %d bài thô", key, n)
    if cmd in ("s2-refs", "all"):
        s2.crawl_references(s2.make_client(), corpus_paper_ids(args.venues), args.batch_size)
    if cmd in ("s2-edges", "all"):
        s2.crawl_edges_sample(s2.make_client(), ids_with_refs(), args.sample)
    if cmd == "openreview-check":
        openreview.check_access()
    if cmd == "openreview":
        for key in args.venues:
            for edition, src in VENUES[key].openreview.items():
                if args.editions and edition not in args.editions:
                    continue
                if args.skip_existing and openreview.raw_path(key, edition).exists():
                    log.info("openreview %s %s: đã có cache, bỏ qua", key, edition)
                    continue
                try:
                    openreview.crawl_source(key, edition, src)
                except Exception:
                    log.exception("openreview %s %s: lỗi, chuyển sang nguồn tiếp theo", key, edition)
    if cmd == "arxiv-refs":
        arxiv.crawl_bbl(arxiv_targets(args.venues, args.limit, args.validate, args.seed), args.interval)
    if cmd in ("load", "all"):
        build_db()


if __name__ == "__main__":
    main()
