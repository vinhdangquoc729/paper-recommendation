"""CLI của module crawler.

    python -m crawler s2-papers               # metadata bài theo venue (vài phút)
    python -m crawler s2-refs                 # reference của mọi bài (lâu nhất)
    python -m crawler s2-edges --sample 300   # intents / isInfluential / contexts cho mẫu bài
    python -m crawler openreview-check        # thử đăng nhập + đọc 1 submission, không cào gì
    python -m crawler openreview              # cần OPENREVIEW_USERNAME / PASSWORD trong .env
    python -m crawler arxiv-refs --limit 100 --validate 30
                                              # reference từ .bbl trên arXiv cho bài S2 ẩn
                                              # (+ một mẫu bài S2 có refs để kiểm tra parser)
    python -m crawler eval-refs --t 2025-01-01 --authors 500
                                              # reference (.bbl arXiv) cho bài sau T của một mẫu tác giả,
                                              # làm ground truth cho đánh giá; cần chạy load trước
    python -m crawler corpus-refs             # reference (.bbl arXiv) cho mọi bài đã có arXiv ID
    python -m crawler corpus-refs --shard 0/3 # chạy song song: 3 terminal với --shard 0/3, 1/3, 2/3
                                              # (khoảng 23.000 bài, 1 đến 1,5 ngày; ngắt và chạy lại được)
    python -m crawler arxiv-oai               # tải metadata arXiv qua OAI-PMH (set cs từ 2022-01), ghép tiêu đề
                                              # + tác giả để có arXiv ID cho bài S2 không gắn (reject / rút / 2026)
    python -m crawler arxiv-oai --skip-harvest  # chỉ ghép lại từ metadata đã tải
    python -m crawler load                    # dựng data/corpus.sqlite từ data/raw/
    python -m crawler all                     # s2-papers -> s2-refs -> s2-edges -> load

Mọi bước đều có cache trong data/raw/, chạy lại chỉ lấy phần còn thiếu.
"""
import argparse
import logging
import random

from common.config import setup_logging
from common.db import connect
from common.jsonl import read_jsonl
from crawler import arxiv, arxiv_ids, arxiv_oai, eval_targets, openreview, s2
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


def known_arxiv_ids(conn) -> dict[str, str]:
    """forum_id -> arXiv ID đã biết: từ bài S2 ghép được, và từ cache tra theo tiêu đề."""
    known = dict(conn.execute("""SELECT o.forum_id, p.arxiv_id FROM or_submissions o
                                 JOIN papers p ON p.paper_id = o.s2_paper_id WHERE p.arxiv_id IS NOT NULL"""))
    for f, r in arxiv_ids.lookup_status().items():
        if r.get("arxiv_id"):
            known.setdefault(f, r["arxiv_id"])
    return known


def run_eval_refs(t: str, n_authors: int, seed: int, interval: float, src_interval: float) -> None:
    conn = connect()
    _, target = eval_targets.select_targets(conn, t, n_authors, seed)
    known = known_arxiv_ids(conn)
    need = [(r.forums[0], r.title) for r in target.itertuples() if not any(f in known for f in r.forums)]
    log.info("[eval] %d / %d bài đã có arXiv ID, tra thêm %d bài theo tiêu đề",
             len(target) - len(need), len(target), len(need))
    arxiv_ids.lookup_arxiv_ids(need, arxiv_interval=interval)

    known = known_arxiv_ids(conn)
    conn.close()
    ids = [next(known[f] for f in r.forums if f in known) for r in target.itertuples()
           if any(f in known for f in r.forums)]
    log.info("[eval] %d / %d bài có arXiv ID, tải .bbl", len(ids), len(target))
    arxiv.crawl_bbl(ids, src_interval)


def run_corpus_refs(t: str, n_authors: int, seed: int, src_interval: float, limit: int | None,
                    shard: tuple[int, int] | None = None) -> None:
    """Giai đoạn 1: tải source LaTeX cho mọi bài trong corpus đã có arXiv ID (không tra thêm theo tiêu đề).

    Bài thuộc tập đánh giá (eval-refs cùng T / số tác giả / seed) được tải trước, sau đó bài mới trước bài cũ.
    """
    conn = connect()
    known = known_arxiv_ids(conn)
    _, target = eval_targets.select_targets(conn, t, n_authors, seed)
    first = {f for fs in target.forums for f in fs}
    rows = conn.execute("SELECT forum_id, edition FROM or_submissions").fetchall()
    conn.close()
    rows = [(f, y) for f, y in rows if f in known]
    rows.sort(key=lambda r: (r[0] not in first, -(r[1] or 0)))
    ids = list(dict.fromkeys(known[f] for f, _ in rows))   # các lần nộp lại có thể chung một arXiv ID
    n_first = len({known[f] for f, _ in rows if f in first})
    log.info("[corpus-refs] %d bài có arXiv ID (%d arXiv ID khác nhau), %d thuộc tập đánh giá được tải trước",
             len(rows), len(ids), n_first)
    arxiv.crawl_bbl(ids[:limit], src_interval, shard=shard)


def parse_shard(text: str) -> tuple[int, int]:
    try:
        i, n = (int(x) for x in text.split("/"))
    except ValueError:
        raise argparse.ArgumentTypeError("dạng I/N, ví dụ 0/3") from None
    if not 0 <= i < n:
        raise argparse.ArgumentTypeError("cần 0 <= I < N")
    return i, n


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m crawler")
    parser.add_argument("command", choices=["s2-papers", "s2-refs", "s2-edges", "openreview", "openreview-check",
                                            "arxiv-refs", "eval-refs", "corpus-refs", "arxiv-oai", "load", "all"])
    parser.add_argument("--venues", nargs="+", default=list(VENUES), choices=list(VENUES))
    parser.add_argument("--editions", nargs="+", type=int, help="chỉ cho lệnh openreview")
    parser.add_argument("--skip-existing", action="store_true", help="openreview: bỏ qua nguồn đã có cache")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--sample", type=int, default=300, help="số bài cho s2-edges")
    parser.add_argument("--limit", type=int,
                        help="arxiv-refs / corpus-refs: số bài tối đa (mặc định: tất cả)")
    parser.add_argument("--validate", type=int, default=0, help="arxiv-refs: số bài S2 có refs để kiểm tra parser")
    parser.add_argument("--interval", type=float, default=0.1,
                        help="giây giữa hai request tới API tìm kiếm arXiv (tra arXiv ID theo tiêu đề)")
    parser.add_argument("--src-interval", type=float, default=arxiv.SRC_MIN_INTERVAL,
                        help="giây giữa hai request tải source LaTeX (arxiv-refs / eval-refs / corpus-refs)")
    parser.add_argument("--shard", type=parse_shard, metavar="I/N",
                        help="corpus-refs: chỉ tải phần I trong N phần (0 <= I < N), để chạy N tiến trình song song")
    parser.add_argument("--oai-sets", nargs="+", default=["cs"], help="arxiv-oai: set OAI-PMH (cs, stat, ...)")
    parser.add_argument("--oai-from", default="2022-01", help="arxiv-oai: tháng bắt đầu (theo ngày cập nhật cuối)")
    parser.add_argument("--skip-harvest", action="store_true", help="arxiv-oai: không tải, chỉ ghép")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--t", default="2025-01-01", help="eval-refs: mốc thời gian T (YYYY-MM-DD)")
    parser.add_argument("--authors", type=int, default=500, help="eval-refs: số tác giả lấy mẫu")
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
        arxiv.crawl_bbl(arxiv_targets(args.venues, args.limit, args.validate, args.seed), args.src_interval)
    if cmd == "eval-refs":
        run_eval_refs(args.t, args.authors, args.seed, args.interval, args.src_interval)
    if cmd == "corpus-refs":
        run_corpus_refs(args.t, args.authors, args.seed, args.src_interval, args.limit, args.shard)
    if cmd == "arxiv-oai":
        if not args.skip_harvest:
            arxiv_oai.harvest(args.oai_sets, args.oai_from)
        conn = connect()
        arxiv_oai.match(conn)
        conn.close()
    if cmd in ("load", "all"):
        build_db()


if __name__ == "__main__":
    main()
