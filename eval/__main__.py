"""CLI đánh giá offline "tác giả là người dùng" (spec mục 12).

    python -m eval gt                                  # thống kê tác giả và ground truth theo split
    python -m eval run                                 # B0..B3 trên tập val
    python -m eval run --split test --gt lead          # báo cáo cuối: tập test, chỉ bài tác giả đứng đầu / cuối
    python -m eval run --methods B2 --limit 300        # thử nhanh
    python -m eval ablation                            # B4-B8 và ablation từng thành phần (học trên train, chấm val)
    python -m eval ablation --no-center                # như trên với embedding gốc (chưa trừ trung bình)

Đọc data/corpus.sqlite và data/features/; ghi reports/eval/*.md và data/eval/*.csv (độ đo từng tác giả).
"""
import argparse
import logging
import time

import numpy as np
import pandas as pd

from common.config import DATA_DIR, REPORTS_DIR, setup_logging
from common.db import connect
from eval import ablation, baselines, run
from eval.hybrid import Cache, FeatureBuilder
from eval.protocol import GT_VARIANTS, SPLITS, build_cases, load_world
from features import store
from features.quality import compute_quality, load_reviews
from recsys.model import MODELS_DIR, LinearModel

log = logging.getLogger("eval")

DEFAULT_T = "2025-01-01"
METHODS = {"B0": lambda w: baselines.Random(), "B1": lambda w: baselines.Popularity(),
           "B2": lambda w: baselines.ContentMean(w), "B3": lambda w: baselines.ContentMulti(w)}


def run_gt(T: str) -> None:
    conn = connect()
    world = load_world(conn, T, with_emb=False)
    conn.close()
    for variant in GT_VARIANTS:
        cases = build_cases(world, variant)
        df = pd.DataFrame([{"split": c.split, "n_gt": len(c.gt), "n_after_refs": c.n_after_refs,
                            "n_profile": len(c.authored) + len(c.prior)} for c in cases])
        print(f"\nground truth = {variant}: {len(df)} tác giả")
        print(df.groupby("split").agg(authors=("n_gt", "size"), gt_median=("n_gt", "median"),
                                      gt_mean=("n_gt", "mean"), gt_ge5=("n_gt", lambda s: (s >= 5).mean()),
                                      profile_median=("n_profile", "median")).round(2).to_markdown())


def quality_at(world, T: str, conn) -> np.ndarray:
    it, versions = store.read_table("items"), store.read_table("versions")
    q = compute_quality(it, versions, load_reviews(conn), as_of=T).set_index("item_id").q
    return q.reindex(world.item_ids).to_numpy()


def run_eval(T: str, split: str, variant: str, methods: list[str], limit: int | None, seed: int,
             center: bool = True) -> None:
    conn = connect()
    world = load_world(conn, T, center=center)
    q = quality_at(world, T, conn)
    conn.close()
    cases = [c for c in build_cases(world, variant) if c.split == split]
    if limit:
        cases = list(np.random.default_rng(seed).permutation(np.array(cases, dtype=object))[:limit])
    log.info("[eval] split=%s, ground truth=%s: %d tác giả", split, variant, len(cases))

    results, cov = {}, {}
    for key in methods:
        method = METHODS[key](world)
        start = time.monotonic()
        df, tops = run.evaluate(world, cases, method, q)
        results[method.name], cov[method.name] = df, run.coverage(world, tops)
        log.info("[eval] %s: ndcg@10 %.4f, recall@20 %.4f (%.0fs)", method.name, df["ndcg@10"].mean(),
                 df["recall@20"].mean(), time.monotonic() - start)

    tag = f"T{T}_{split}_{variant}" + (f"_n{limit}" if limit else "") + ("_c" if center else "")
    out_dir = DATA_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.concat([df.assign(method=n) for n, df in results.items()]).to_csv(out_dir / f"{tag}.csv", index=False)

    summary = run.summarize(results, cov).to_markdown(index=False)
    ref = next(iter(results))
    cmp = run.compare(results, ref).round(4).to_markdown(index=False) if len(results) > 1 else ""
    report = (f"# Đánh giá offline T={T}, split={split}, ground truth={variant}\n\n"
              f"{len(cases)} tác giả, pool {len(world.pool)} bài. "
              f"Độ đo ngoài độ chính xác tính trên top-{run.K_BEYOND}.\n\n{summary}\n\n{cmp}\n")
    path = REPORTS_DIR / "eval" / f"{tag}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Đã ghi {path}")


def _cache(builder: FeatureBuilder, cases, path, rebuild: bool) -> Cache:
    if path.exists() and not rebuild:
        cache = Cache.load(path)
        if cache.authors == [c.author for c in cases]:
            log.info("[eval] dùng lại %s", path)
            return cache
    cache = builder.build(cases)
    cache.save(path)
    return cache


def run_ablation(T: str, variant: str, n_train: int, limit: int | None, seed: int, rebuild: bool,
                 objective: str = "binary", center: bool = True) -> None:
    conn = connect()
    world = load_world(conn, T, center=center)
    q = quality_at(world, T, conn)
    conn.close()
    cases = build_cases(world, variant)
    rng = np.random.default_rng(seed)
    train = [c for c in cases if c.split == "train"]
    train = [train[i] for i in sorted(rng.permutation(len(train))[:n_train])]
    val = [c for c in cases if c.split == "val"]
    if limit:
        val = [val[i] for i in sorted(rng.permutation(len(val))[:limit])]
    log.info("[eval] ablation: %d tác giả train, %d tác giả val", len(train), len(val))

    base = {"results": {}, "coverage": {}}
    for key in ("B1", "B3"):
        method = METHODS[key](world)
        df, tops = run.evaluate(world, val, method, q)
        base["results"][method.name], base["coverage"][method.name] = df, run.coverage(world, tops)

    out_dir = DATA_DIR / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    builder = FeatureBuilder(world, q)
    tag = f"T{T}_{variant}_s{seed}" + ("_c" if center else "")    # _c: embedding đã trừ trung bình
    tr_cache = _cache(builder, train, out_dir / f"hybrid_{tag}_train{n_train}.npz", rebuild)
    va_cache = _cache(builder, val, out_dir / f"hybrid_{tag}_val{limit or 'all'}.npz", rebuild)
    cover = lambda c: 100 * (c.y.sum(1) / c.n_gt).mean()

    results, cov, weights, learned = ablation.run_ablation(world, q, tr_cache, train, va_cache, val, base, objective)
    tag += f"_{objective}"
    b6 = next(n for n in learned if n.startswith("B6 đủ"))
    w6, train_ndcg = learned[b6]
    model = LinearModel(f"{b6} [{objective}]", list(w6), [float(v) for v in w6.values()],
                        {"T": T, "ground_truth": variant, "objective": objective, "train_authors": len(train),
                         "ndcg@10_train": round(train_ndcg, 4),
                         "ndcg@10_val": round(float(results[b6]["ndcg@10"].mean()), 4),
                         "ndcg@10g_val": round(float(results[b6]["ndcg@10g"].mean()), 4)})
    model.info["center_emb"] = center
    model_path = MODELS_DIR / f"linear_b6_{objective}{'_c' if center else ''}.json"
    model.save(model_path)
    log.info("[eval] đã lưu mô hình %s", model_path)
    pd.concat([df.assign(method=n) for n, df in results.items()]).to_csv(
        out_dir / f"ablation_{tag}_val.csv", index=False)

    names = list(results)
    pick = lambda prefix: next(n for n in names if n.startswith(prefix))
    b4, b6 = pick("B4"), pick("B6 đủ")
    pairs = ([(b4, n) for n in names if n.startswith("B5 + đồ thị lọc")]
             + [(pick("B6 nhưng"), b6), (pick("B1"), b6), (pick("B3"), pick("C0"))]
             + [(b6, n) for n in names if n.startswith(("B6 bỏ", "B7", "B8"))])
    cmp = pd.concat([run.compare({a: results[a], b: results[b]}, a, m) for m in ("ndcg@10", "ndcg@10g")
                     for a, b in pairs]).round(4)

    summary = run.summarize(results, cov).to_markdown(index=False)
    pairs_md = cmp.rename(columns={"vs": "a", "method": "b"}).to_markdown(index=False)
    report = (f"# Ablation T={T}, ground truth={variant}, học theo mục tiêu {objective}\n\n"
              f"Học trọng số trên {len(train)} tác giả train, chấm trên {len(val)} tác giả val, pool {len(world.pool)} bài. "
              f"Mỗi tác giả khoảng {va_cache.valid.sum(1).mean():.0f} ứng viên, phủ {cover(va_cache):.1f}% ground truth "
              f"(train: {cover(tr_cache):.1f}%). B1, B3 xếp hạng toàn pool.\n\n"
              f"## Kết quả\n\n{summary}\n\n"
              f"## So sánh cặp (b - a)\n\n{pairs_md}\n\n"
              f"## Trọng số đã học\n\n{weights.fillna('').to_markdown(index=False)}\n")
    path = REPORTS_DIR / "eval" / f"ablation_{tag}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Đã ghi {path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m eval")
    parser.add_argument("command", choices=["gt", "run", "ablation"])
    parser.add_argument("--t", default=DEFAULT_T, help="mốc thời gian T (YYYY-MM-DD)")
    parser.add_argument("--split", default="val", choices=[s for s, _ in SPLITS],
                        help="val khi đang chỉnh; test chỉ dùng cho báo cáo cuối")
    parser.add_argument("--gt", default="all", choices=GT_VARIANTS,
                        help="all: mọi bài sau T; lead: chỉ bài tác giả đứng đầu hoặc cuối")
    parser.add_argument("--methods", default="B0,B1,B2,B3", help="danh sách cấu hình, cách nhau bởi dấu phẩy")
    parser.add_argument("--limit", type=int, help="chỉ lấy ngẫu nhiên N tác giả (thử nhanh)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--train-authors", type=int, default=2500, help="ablation: số tác giả train để học trọng số")
    parser.add_argument("--rebuild", action="store_true", help="ablation: tính lại đặc trưng dù đã có cache")
    parser.add_argument("--objective", default="binary", choices=["binary", "graded"],
                        help="ablation: học trọng số theo ground truth nhị phân hay nhiều mức (bài trích cho có = 0)")
    parser.add_argument("--no-center", dest="center", action="store_false",
                        help="dùng embedding gốc, không trừ vector trung bình của pool")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "gt":
        run_gt(args.t)
    elif args.command == "ablation":
        run_ablation(args.t, args.gt, args.train_authors, args.limit, args.seed, args.rebuild, args.objective,
                     args.center)
    else:
        methods = [m.strip() for m in args.methods.split(",")]
        unknown = set(methods) - set(METHODS)
        if unknown:
            parser.error(f"không có cấu hình {sorted(unknown)}; có: {sorted(METHODS)}")
        run_eval(args.t, args.split, args.gt, methods, args.limit, args.seed, args.center)


if __name__ == "__main__":
    main()
