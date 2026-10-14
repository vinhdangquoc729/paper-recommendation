"""Phân tích độ thưa của corpus: dữ liệu có đủ cho từng khối trong spec không.

Mỗi hàm `section_*` nhận dữ liệu đã nạp, ghi một mục vào Report.
"""
import json
import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
import scipy.sparse as sp

from analysis.report import Report, pct

log = logging.getLogger(__name__)

HUB_QUANTILE = 0.999
SPLIT_DATES = ["2024-07-01", "2025-01-01", "2025-07-01"]
DIGEST_WINDOWS = [30, 90]


@dataclass
class Data:
    papers: pd.DataFrame      # corpus
    pa: pd.DataFrame          # paper_id, author_id, position
    cit: pd.DataFrame         # citing_id, cited_id (mọi reference, cited_id có thể NULL)
    cit_in: pd.DataFrame      # cạnh có cả hai đầu trong corpus, kèm cờ self (chung tác giả)
    meta: pd.DataFrame        # citation_meta (mẫu)
    meta_papers: pd.DataFrame
    or_subs: pd.DataFrame
    or_reviews: pd.DataFrame
    bbl_papers: pd.DataFrame
    bbl_refs: pd.DataFrame


def load(conn) -> Data:
    papers = pd.read_sql(
        "SELECT paper_id, title, venue_key, edition, pub_date, avail_date, arxiv_id, "
        "abstract IS NOT NULL AND abstract != '' AS has_abstract, citation_count, reference_count, "
        "n_refs_returned, refs_status FROM papers", conn, parse_dates=["avail_date"])
    pa = pd.read_sql("SELECT paper_id, author_id, position FROM paper_authors", conn)
    cit = pd.read_sql("SELECT citing_id, cited_id FROM citations", conn).drop_duplicates()
    corpus = set(papers.paper_id)
    cit_in = cit[cit.cited_id.isin(corpus) & cit.citing_id.isin(corpus)].copy()

    # Cạnh "tự trích" = bài citing và cited có chung ít nhất một tác giả
    a = pa[["paper_id", "author_id"]]
    shared = (cit_in.merge(a.rename(columns={"paper_id": "citing_id"}), on="citing_id")
              .merge(a.rename(columns={"paper_id": "cited_id"}), on=["cited_id", "author_id"]))
    self_pairs = set(zip(shared.citing_id, shared.cited_id))
    cit_in["self"] = [(c, d) in self_pairs for c, d in zip(cit_in.citing_id, cit_in.cited_id)]

    def opt(sql):
        try:
            return pd.read_sql(sql, conn)
        except Exception:  # bảng chưa có
            return pd.DataFrame()

    return Data(
        papers=papers, pa=pa, cit=cit, cit_in=cit_in,
        meta=opt("SELECT * FROM citation_meta"),
        meta_papers=opt("SELECT * FROM citation_meta_papers"),
        or_subs=opt("SELECT * FROM or_submissions"),
        or_reviews=opt("SELECT * FROM or_reviews"),
        bbl_papers=opt("SELECT * FROM bbl_papers"),
        bbl_refs=opt("SELECT * FROM bbl_refs"),
    )


# ---------------------------------------------------------------- 1. Tổng quan

def section_overview(d: Data, r: Report) -> None:
    r.h2("1. Tổng quan corpus (Semantic Scholar, bài đã accept)")
    p = d.papers
    rows = []
    for (venue, ed), g in list(p.groupby(["venue_key", "edition"])) + [(("TỔNG", ""), p)]:
        rows.append({
            "venue": venue, "edition": ed, "số bài": len(g),
            "có abstract": pct(g.has_abstract.mean()),
            "có arXiv": pct(g.arxiv_id.notna().mean()),
            "có ngày công bố": pct(g.pub_date.notna().mean()),
            "refs ok": pct((g.refs_status == "ok").mean()),
            "refs bị ẩn": pct((g.refs_status == "elided").mean()),
            "refs rỗng/không thấy": pct(g.refs_status.isin(["empty", "not_found"]).mean()),
            "chưa cào refs": pct(g.refs_status.isna().mean()),
            "median #refs (bài ok)": g.loc[g.refs_status == "ok", "n_refs_returned"].median(),
            "median citation": g.citation_count.median(),
        })
    r.table(pd.DataFrame(rows))
    r.stat("n_papers", len(p))
    r.stat("frac_refs_ok", (p.refs_status == "ok").mean())
    r.stat("frac_refs_elided", (p.refs_status == "elided").mean())

    n_auth = d.pa.groupby("author_id").size()
    r.h3("Số bài mỗi tác giả (S2 author ID)")
    r.bullets({
        "số tác giả": f"{len(n_auth):,}",
        "chỉ có 1 bài": pct((n_auth == 1).mean()),
        "≥ 3 bài": f"{(n_auth >= 3).sum():,} ({pct((n_auth >= 3).mean())})",
        "≥ 5 bài": f"{(n_auth >= 5).sum():,} ({pct((n_auth >= 5).mean())})",
    })
    r.text("> Lưu ý: S2 hay tách một người thành nhiều author ID, nên số liệu tác giả là cận dưới về độ dày hồ sơ.")
    r.stat("n_authors", len(n_auth))
    r.stat("n_authors_ge3", int((n_auth >= 3).sum()))


# ---------------------------------------------------------------- 2. Reference

def section_references(d: Data, r: Report) -> None:
    r.h2("2. Reference: phân giải được bao nhiêu, rơi vào corpus bao nhiêu")
    ok = d.papers[d.papers.refs_status == "ok"]
    cit = d.cit[d.cit.citing_id.isin(ok.paper_id)]
    resolved = cit.cited_id.notna()
    in_corpus = cit.cited_id.isin(set(d.papers.paper_id))
    r.bullets({
        "bài có reference": f"{len(ok):,}",
        "tổng số cạnh reference": f"{len(cit):,}",
        "S2 phân giải được (có paperId)": pct(resolved.mean()),
        "cạnh trỏ vào corpus": f"{in_corpus.sum():,} ({pct(in_corpus.mean())})",
    })
    r.text("Tỉ lệ cạnh trỏ vào corpus là **trần** cho mọi ground truth dạng \"tác giả trích bài nào trong corpus\": "
           "phần còn lại là bài ngoài các venue trong corpus.")
    r.stat("frac_refs_resolved", resolved.mean())
    r.stat("frac_refs_in_corpus", in_corpus.mean())

    outdeg = d.cit_in.groupby("citing_id").size().reindex(ok.paper_id, fill_value=0)
    tab = (pd.DataFrame({"edition": ok.edition.values, "venue": ok.venue_key.values, "deg": outdeg.values})
           .groupby(["venue", "edition"]).deg
           .agg(mean="mean", median="median", p90=lambda s: s.quantile(0.9), zero=lambda s: pct((s == 0).mean()))
           .reset_index())
    r.h3("Số reference trong corpus của mỗi bài (out-degree nội corpus)")
    r.table(tab.rename(columns={"zero": "% bài = 0"}))
    r.stat("outdeg_in_corpus_mean", outdeg.mean())
    r.stat("outdeg_in_corpus_zero", (outdeg == 0).mean())


# ---------------------------------------------------------------- 3. In-degree, hub

def section_indegree(d: Data, r: Report) -> None:
    r.h2("3. Bài trong corpus được trích bao nhiêu lần (trong corpus) và hub")
    indeg = d.cit_in.groupby("cited_id").size().reindex(d.papers.paper_id, fill_value=0)
    tab = (pd.DataFrame({"venue": d.papers.venue_key.values, "edition": d.papers.edition.values, "deg": indeg.values})
           .groupby(["venue", "edition"]).deg
           .agg(mean="mean", median="median", zero=lambda s: pct((s == 0).mean()),
                ge5=lambda s: pct((s >= 5).mean()))
           .reset_index().rename(columns={"zero": "% chưa ai trích", "ge5": "% ≥ 5 lần"}))
    r.table(tab)
    r.text("Bài chưa được trích trong corpus thì **không có co-citation** và không có tín hiệu citation velocity.")
    r.stat("indeg_zero_frac", (indeg == 0).mean())

    ok_ids = set(d.papers.loc[d.papers.refs_status == "ok", "paper_id"])
    cit = d.cit[d.cit.citing_id.isin(ok_ids) & d.cit.cited_id.notna()]
    deg = cit.groupby("cited_id").size()
    thr = deg.quantile(HUB_QUANTILE)
    hubs = deg[deg >= thr]
    r.h3("Hub (reference được trích nhiều nhất)")
    r.bullets({
        "số reference khác nhau": f"{len(deg):,}",
        "reference chỉ được 1 bài trích": pct((deg == 1).mean()),
        f"ngưỡng hub (phân vị {HUB_QUANTILE:.1%})": f"≥ {thr:.0f} bài trích",
        "số hub": len(hubs),
        "tỉ lệ cạnh trỏ vào hub": pct(hubs.sum() / deg.sum()),
    })
    top = hubs.sort_values(ascending=False).head(10).rename("số bài trích").reset_index()
    titles = d.papers.set_index("paper_id").title
    top["trong corpus?"] = top.cited_id.map(lambda x: titles.get(x, "— (ngoài corpus)"))
    r.table(top)
    r.stat("hub_threshold", thr)
    r.stat("frac_edges_to_hubs", hubs.sum() / deg.sum())


# ---------------------------------------------------------------- 4. Coupling

def _neighbor_counts(A: sp.csr_matrix, chunk: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Với mỗi hàng: số hàng khác chung ≥1 cột và chung ≥2 cột (không dựng cả ma trận A·Aᵀ)."""
    At = A.T.tocsc()
    deg = np.diff(A.indptr)
    n1, n2 = np.zeros(A.shape[0], int), np.zeros(A.shape[0], int)
    for s in range(0, A.shape[0], chunk):
        B = (A[s:s + chunk] @ At).tocsr()
        n1[s:s + chunk] = np.diff(B.indptr)
        B.data = (B.data >= 2).astype(np.int8)
        B.eliminate_zeros()
        n2[s:s + chunk] = np.diff(B.indptr)
    # bỏ chính nó (đường chéo = số reference của bài)
    return n1 - (deg >= 1), n2 - (deg >= 2)


def _incidence(rows: pd.Series, cols: pd.Series, row_index: pd.Index, col_index: pd.Index) -> sp.csr_matrix:
    ri = row_index.get_indexer(rows)
    ci = col_index.get_indexer(cols)
    m = (ri >= 0) & (ci >= 0)
    A = sp.csr_matrix((np.ones(m.sum(), np.float32), (ri[m], ci[m])), shape=(len(row_index), len(col_index)))
    A.data[:] = 1
    return A


def section_coupling(d: Data, r: Report) -> None:
    r.h2("4. Bibliographic coupling (chung reference, kể cả reference ngoài corpus)")
    ok = d.papers[d.papers.refs_status == "ok"].reset_index(drop=True)
    cit = d.cit[d.cit.citing_id.isin(set(ok.paper_id)) & d.cit.cited_id.notna()]
    deg = cit.groupby("cited_id").size()
    thr = deg.quantile(HUB_QUANTILE)
    rows = pd.Index(ok.paper_id)
    out, by_edition = [], None
    for name, keep in [("mọi reference", deg.index), ("bỏ hub", deg.index[deg < thr])]:
        c = cit[cit.cited_id.isin(keep)]
        A = _incidence(c.citing_id, c.cited_id, rows, pd.Index(keep))
        n1, n2 = _neighbor_counts(A)
        cost = float((deg.loc[keep] ** 2).sum())
        out.append({
            "biến thể": name,
            "chi phí Σ deg_in²": f"{cost:,.0f}",
            "% bài có ≥1 láng giềng": pct((n1 > 0).mean()),
            "median #láng giềng (≥1 ref chung)": np.median(n1),
            "% bài có ≥10 láng giềng chung ≥2 ref": pct((n2 >= 10).mean()),
            "median #láng giềng (≥2 ref chung)": np.median(n2),
        })
        r.stat(f"coupling[{name}]_frac_ge1", (n1 > 0).mean())
        r.stat(f"coupling[{name}]_median_n2", np.median(n2))
        if name == "bỏ hub":
            by_edition = (pd.DataFrame({"venue": ok.venue_key, "edition": ok.edition, "n2": n2})
                          .groupby(["venue", "edition"]).n2
                          .agg(median="median", ge10=lambda s: pct((s >= 10).mean()), zero=lambda s: pct((s == 0).mean()))
                          .reset_index().rename(columns={"median": "median #láng giềng ≥2 ref",
                                                         "ge10": "% ≥10", "zero": "% = 0"}))
    r.table(pd.DataFrame(out))
    r.h3("Theo edition (bỏ hub, láng giềng chung ≥ 2 reference)")
    r.table(by_edition)
    r.text("Coupling chỉ cần reference của chính bài nên **dùng được ngay cho bài mới** (miễn S2 trả reference).")


# ---------------------------------------------------------------- 5. Co-citation

def section_cocitation(d: Data, r: Report) -> None:
    r.h2("5. Co-citation trong corpus")
    ids = pd.Index(d.papers.paper_id)
    A = _incidence(d.cit_in.citing_id, d.cit_in.cited_id, ids, ids)   # citing × cited
    n1, n2 = _neighbor_counts(A.T.tocsr())
    tab = (pd.DataFrame({"venue": d.papers.venue_key, "edition": d.papers.edition, "n1": n1, "n2": n2})
           .groupby(["venue", "edition"])
           .agg(ge1=("n1", lambda s: pct((s > 0).mean())), med1=("n1", "median"),
                ge1_2=("n2", lambda s: pct((s > 0).mean())))
           .reset_index().rename(columns={"ge1": "% có ≥1 bài đồng trích", "med1": "median #đồng trích",
                                          "ge1_2": "% có bài đồng trích ≥2 lần"}))
    r.table(tab)
    r.stat("cocitation_frac_ge1", (n1 > 0).mean())
    r.text("Co-citation chỉ tính từ bài citing **trong corpus**. Muốn dày hơn phải lấy citation từ toàn bộ S2 "
           "(endpoint /citations, tốn thêm nhiều request).")


# ---------------------------------------------------------------- 6. Giao thức tác giả = người dùng

def section_author_protocol(d: Data, r: Report) -> None:
    r.h2("6. Giao thức \"tác giả là người dùng\" (Mục 12.1 trong spec)")
    r.text("- Hồ sơ tại T: bài `authored` có ngày < T.\n"
           "- Ground truth (GT): bài trong corpus được trích bởi bài của tác giả đăng ≥ T, "
           "loại bài đã trích trước T và bài của chính tác giả.\n"
           "- GT nghiêm: bỏ thêm cạnh tự trích (bài citing và cited có chung tác giả bất kỳ, "
           "tức gồm cả trích bài của đồng tác giả).\n"
           "- GT digest Δ: chỉ giữ GT có ngày trong [T, T+Δ).\n"
           "- Ngày của bài = `publicationDate` trên S2 (thường là ngày lên arXiv).")
    pa = d.pa.merge(d.papers[["paper_id", "avail_date", "refs_status"]], on="paper_id")
    avail = d.papers.set_index("paper_id").avail_date
    own = set(zip(d.pa.author_id, d.pa.paper_id))
    cit_all = d.cit[d.cit.cited_id.notna()]
    corpus = set(d.papers.paper_id)

    rows, gt_rows = [], []
    for T in SPLIT_DATES:
        t = pd.Timestamp(T)
        pa["after"] = pa.avail_date >= t
        cnt = pa.groupby("author_id").agg(n=("paper_id", "size"), n_after=("after", "sum"))
        cnt["n_before"] = cnt.n - cnt.n_after
        spec_ok = (cnt.n >= 3) & (cnt.n_after >= 1)
        elig = spec_ok & (cnt.n_before >= 1)
        rows.append({
            "T": T,
            "≥3 bài & ≥1 sau T (spec)": f"{spec_ok.sum():,}",
            "+ ≥1 bài trước T": f"{elig.sum():,}",
            "+ ≥2 bài trước T": f"{(spec_ok & (cnt.n_before >= 2)).sum():,}",
        })

        E = cnt.index[elig]
        ea = pa[pa.author_id.isin(E)]
        has_ok_after = ea[ea.after & (ea.refs_status == "ok")].author_id.unique()
        edges = ea.merge(d.cit_in, left_on="paper_id", right_on="citing_id")
        known = set(zip(edges.loc[~edges.after, "author_id"], edges.loc[~edges.after, "cited_id"]))

        def gt(e):
            pairs = set(zip(e.author_id, e.cited_id)) - known
            return {(a, p) for a, p in pairs if (a, p) not in own}

        post = edges[edges.after]
        variants = {"GT": gt(post), "GT nghiêm": gt(post[~post.self])}
        for delta in DIGEST_WINDOWS:
            hi = t + pd.Timedelta(days=delta)
            variants[f"GT digest {delta}d (nghiêm)"] = {
                (a, p) for a, p in variants["GT nghiêm"] if t <= avail[p] < hi}

        for name, pairs in variants.items():
            sizes = pd.Series([a for a, _ in pairs]).value_counts().reindex(E, fill_value=0)
            gt_rows.append({
                "T": T, "loại": name,
                "% tác giả có GT ≥1": pct((sizes >= 1).mean()),
                "% có GT ≥5": pct((sizes >= 5).mean()),
                "mean": sizes.mean(), "median": sizes.median(),
            })
            r.stat(f"protocol[{T}][{name}]_frac_ge1", (sizes >= 1).mean())

        # trần recall: trong reference của các bài sau T, bao nhiêu nằm trong corpus
        post_refs = cit_all[cit_all.citing_id.isin(set(ea.loc[ea.after, "paper_id"]))]
        gt_rows[-len(variants)]["trần: % ref sau T thuộc corpus"] = pct(post_refs.cited_id.isin(corpus).mean())
        gt_rows[-len(variants)]["% tác giả có bài sau T lấy được refs"] = pct(len(has_ok_after) / max(len(E), 1))
        r.stat(f"protocol[{T}]_n_eligible", int(elig.sum()))

    r.h3("Số tác giả đủ điều kiện")
    r.table(pd.DataFrame(rows))
    r.h3("Kích thước ground truth mỗi tác giả (trên tập đủ điều kiện có ≥1 bài trước T)")
    r.table(pd.DataFrame(gt_rows).fillna(""))


# ---------------------------------------------------------------- 7. Tính mới: phân bố theo thời gian

def _weekly_stats(dates: pd.Series, start: str) -> dict:
    s = dates.dropna()
    s = s[s >= pd.Timestamp(start)]
    weekly = s.dt.to_period("W").value_counts().sort_index()
    full = weekly.reindex(pd.period_range(weekly.index.min(), weekly.index.max(), freq="W"), fill_value=0)
    top5 = full.sort_values(ascending=False).head(5)
    return {
        "số tuần": len(full),
        "median bài/tuần": f"{full.median():.0f}",
        "% tuần < 20 bài": pct((full < 20).mean()),
        "% bài rơi vào 5 tuần đông nhất": pct(top5.sum() / full.sum()),
        "5 tuần đông nhất": ", ".join(f"{p.start_time:%Y-%m-%d} ({v:,})" for p, v in top5.items()),
    }


def section_freshness(d: Data, r: Report) -> None:
    r.h2("7. Luồng bài mới theo tuần (ảnh hưởng tới digest 7 ngày)")
    r.h3("Theo ngày S2 (publicationDate, thường là ngày lên arXiv)")
    st = _weekly_stats(d.papers.avail_date, "2023-01-01")
    r.bullets(st)
    if not d.or_subs.empty:
        r.h3("Theo ngày công khai trên OpenReview (odate → pdate → cdate)")
        dates = pd.to_datetime(d.or_subs.odate.fillna(d.or_subs.pdate).fillna(d.or_subs.cdate), errors="coerce")
        r.bullets(_weekly_stats(dates, "2022-09-01"))
    else:
        r.text("_Chưa có dữ liệu OpenReview: chưa đo được mức dồn cục theo ngày mở submission._")


# ---------------------------------------------------------------- 8. Ma trận user–item

def section_matrix(d: Data, r: Report) -> None:
    r.h2("8. Độ dày ma trận người dùng × bài báo")
    authored = d.pa[["author_id", "paper_id"]]
    cited = (d.pa[["author_id", "paper_id"]].merge(d.cit_in, left_on="paper_id", right_on="citing_id")
             [["author_id", "cited_id"]].rename(columns={"cited_id": "paper_id"}))
    inter = pd.concat([authored, cited]).drop_duplicates()
    n_u, n_i = inter.author_id.nunique(), len(d.papers)
    per_user = inter.groupby("author_id").size()
    active = per_user[per_user.index.isin(d.pa.groupby("author_id").size().loc[lambda s: s >= 3].index)]
    r.bullets({
        "người dùng (tác giả)": f"{n_u:,}",
        "bài báo": f"{n_i:,}",
        "tương tác (authored ∪ cited trong corpus)": f"{len(inter):,}",
        "mật độ": f"{len(inter) / (n_u * n_i):.2e}",
        "median tương tác / người dùng": f"{per_user.median():.0f}",
        "median tương tác / tác giả ≥3 bài": f"{active.median():.0f}",
    })
    r.stat("matrix_density", len(inter) / (n_u * n_i))


# ---------------------------------------------------------------- 9. Đặc trưng cạnh (mẫu)

def section_edge_meta(d: Data, r: Report) -> None:
    r.h2("9. Đặc trưng cạnh từ S2 (mẫu): đủ để lọc reference nhiễu (V3) không?")
    if d.meta_papers.empty:
        r.text("_Chưa cào mẫu s2-edges._")
        return
    m = d.meta
    intents = m.intents.map(json.loads)
    flat = pd.Series([i for lst in intents for i in lst]).value_counts()
    r.bullets({
        "số bài trong mẫu": len(d.meta_papers),
        "bài bị ẩn reference ở endpoint này": pct(d.meta_papers.elided.mean()),
        "số cạnh": f"{len(m):,}",
        "isInfluential = true": pct(m.is_influential.mean()),
        "có ít nhất 1 intent": pct(intents.map(bool).mean()),
        "có ít nhất 1 context": pct((m.n_contexts > 0).mean()),
        "chỉ đúng 1 context": pct((m.n_contexts == 1).mean()),
        "≥ 3 context (nhắc nhiều lần)": pct((m.n_contexts >= 3).mean()),
        "phân bố intent": ", ".join(f"{k}: {pct(v / len(m))}" for k, v in flat.items()),
    })
    r.stat("edge_frac_influential", m.is_influential.mean())
    r.stat("edge_frac_has_intent", intents.map(bool).mean())
    r.stat("edge_frac_has_context", (m.n_contexts > 0).mean())
    r.text("Số context xấp xỉ `mention_count` trong spec; nếu độ phủ context cao thì có thể bỏ GROBID.")


# ---------------------------------------------------------------- 10. OpenReview

def section_openreview(d: Data, r: Report) -> None:
    r.h2("10. OpenReview: review, decision, danh tính tác giả")
    if d.or_subs.empty:
        r.text("_Chưa cào OpenReview (cần OPENREVIEW_USERNAME / OPENREVIEW_PASSWORD trong .env)._")
        return
    s = d.or_subs.copy()
    s["authors_visible"] = s.authorids.map(lambda x: bool(json.loads(x or "[]")))
    rated = d.or_reviews.dropna(subset=["rating"]).groupby("forum_id").size()
    s["n_rated"] = s.forum_id.map(rated).fillna(0)
    rows = []
    for (v, e), g in s.groupby(["venue_key", "edition"]):
        rows.append({
            "venue": v, "edition": e, "submission": len(g),
            "thấy tác giả": pct(g.authors_visible.mean()),
            "có review": pct((g.n_reviews > 0).mean()),
            "có rating số": pct((g.n_rated > 0).mean()),
            "accept": pct(g.decision.fillna("").str.startswith("accept").mean()),
            "reject": pct((g.decision == "reject").mean()),
            "withdrawn": pct((g.decision == "withdrawn").mean()),
            "chưa rõ": pct(g.decision.isna().mean()),
            "nối được sang S2": pct(g.s2_paper_id.notna().mean()),
        })
    r.table(pd.DataFrame(rows))


# ---------------------------------------------------------------- 11. Reference từ arXiv .bbl

def section_arxiv_bbl(d: Data, r: Report) -> None:
    r.h2("11. Reference từ source LaTeX trên arXiv (.bbl)")
    if d.bbl_papers.empty:
        r.text("_Chưa chạy `python -m crawler arxiv-refs`._")
        return
    bp = d.bbl_papers.merge(d.papers[["paper_id", "refs_status", "reference_count"]], on="paper_id", how="left")
    refs = d.bbl_refs
    status = bp.status.value_counts(normalize=True)
    ok = bp[bp.status == "ok"]
    r.bullets({
        "số bài đã tải": len(bp),
        "trạng thái": ", ".join(f"{k}: {pct(v)}" for k, v in status.items()),
        "thời gian thực tế / bài": f"{bp.seconds.mean():.1f} s (median {bp.seconds.median():.1f} s)",
        "dung lượng gói source (median)": f"{bp.bytes.median() / 1e6:.1f} MB",
        "số reference / bài có .bbl (median)": f"{ok.n_items.median():.0f}",
        "tỉ lệ so với referenceCount của S2 (median)": f"{(ok.n_items / ok.reference_count).median():.2f}",
        "reference tách được tiêu đề": pct(refs.title.notna().mean()),
        "reference có arXiv ID": pct(refs.ref_arxiv_id.notna().mean()),
        "reference khớp vào corpus": f"{pct(refs.cited_id.notna().mean())} "
                                     f"(theo arXiv ID {pct((refs.match_by == 'arxiv').mean())}, "
                                     f"theo tiêu đề {pct((refs.match_by == 'title').mean())})",
    })

    # Kiểm tra parser trên các bài S2 có reference: so tập bài-trong-corpus của hai nguồn
    val = ok[ok.refs_status == "ok"].paper_id
    if len(val):
        s2_pairs = set(zip(*d.cit_in[d.cit_in.citing_id.isin(set(val))][["citing_id", "cited_id"]].values.T))
        bbl_in = refs[refs.citing_id.isin(set(val)) & refs.cited_id.notna()]
        bbl_pairs = set(zip(bbl_in.citing_id, bbl_in.cited_id))
        inter = len(s2_pairs & bbl_pairs)
        r.h3(f"Đối chiếu với S2 trên {len(val)} bài S2 có reference (cạnh trỏ vào corpus)")
        r.bullets({
            "cạnh theo S2": len(s2_pairs),
            "cạnh theo .bbl": len(bbl_pairs),
            "precision (.bbl đúng theo S2)": pct(inter / max(len(bbl_pairs), 1)),
            "recall (.bbl tìm lại được cạnh của S2)": pct(inter / max(len(s2_pairs), 1)),
        })
        r.stat("bbl_precision_vs_s2", inter / max(len(bbl_pairs), 1))
        r.stat("bbl_recall_vs_s2", inter / max(len(s2_pairs), 1))

    elided = d.papers[d.papers.refs_status == "elided"]
    trial = ok[ok.refs_status == "elided"]
    n_ax = elided.arxiv_id.notna().sum()
    hours = n_ax * bp.seconds.mean() / 3600
    r.h3("Ước lượng nếu chạy cho toàn bộ bài bị S2 ẩn")
    r.bullets({
        "bài bị ẩn": f"{len(elided):,}",
        "trong đó có arXiv ID": f"{n_ax:,} ({pct(n_ax / max(len(elided), 1))})",
        "thời gian ước tính": f"~{hours:.1f} giờ ở tốc độ hiện tại",
        "bài bị ẩn lấy lại được reference (trong mẫu)": pct((bp[bp.refs_status == "elided"].status == "ok").mean()),
        "cạnh vào corpus / bài (mẫu bị ẩn, từ .bbl)":
            f"{refs[refs.citing_id.isin(set(trial.paper_id))].cited_id.notna().sum() / max(len(trial), 1):.1f}",
    })
    r.stat("bbl_hours_full", hours)


SECTIONS = [section_overview, section_references, section_indegree, section_coupling, section_cocitation,
            section_author_protocol, section_freshness, section_matrix, section_edge_meta, section_openreview,
            section_arxiv_bbl]


def run(conn) -> Report:
    d = load(conn)
    r = Report("Báo cáo độ thưa dữ liệu")
    r.text(f"_Sinh tự động bởi `python -m analysis`, ngày {pd.Timestamp.now():%Y-%m-%d}._")
    for section in SECTIONS:
        log.info("phân tích: %s", section.__name__)
        section(d, r)
    return r
