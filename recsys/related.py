"""Gợi ý theo bài ("Có thể bạn quan tâm" dưới trang đọc bài): bài liên quan tới một bài, có cá nhân hoá nếu biết người dùng.

1. Ứng viên: hợp các nguồn quanh bài đang đọc (nội dung gần, hay được trích cùng, chung reference, trích trực tiếp
   theo cả hai chiều, cùng tác giả). Loại bài không phải ứng viên và bài người dùng đã biết / đã ẩn.
2. Đặc trưng chuẩn hoá trong danh sách ứng viên (recsys.ranking.standardize), cộng theo RELATED_WEIGHTS (đặt tay;
   chưa có đánh giá offline cho bài toán này). Đã đăng nhập thì thêm độ gần với hồ sơ (hồ sơ đa sở thích).
3. MMR để bớt các bài gần như trùng nhau; lý do từ các thành phần đóng góp nhiều nhất, quan hệ trích trực tiếp đứng trước.

Bài chưa có reference (phần lớn bài 2026) vẫn có gợi ý: các đặc trưng đồ thị bằng 0, còn nội dung, tác giả, hồ sơ.
"""
import numpy as np

from recsys import profile
from recsys.ranking import standardize
from recsys.rerank import mmr

# số ứng viên lấy từ mỗi nguồn
SOURCES = {"sim": 100, "cocit_w": 50, "coupling_w": 50, "direct": 100, "coauthor": 50}
RELATED_WEIGHTS = {"sim": 1.0, "cocit_w": 0.75, "coupling_w": 0.5, "direct": 1.0, "coauthor": 0.5, "profile": 0.5,
                   "q": 0.25}
REASON_CODES = {"sim": "similar_content", "cocit_w": "cocited_with_this", "coupling_w": "shares_refs_with_this",
                "coauthor": "same_author", "profile": "similar_to_profile", "q": "high_quality"}
DIRECT_CODES = ("cited_by_this", "cites_this")


def related(rec, paper_id: str, case, k: int = 10, diversity: float = 0.3, n_reasons: int = 2) -> list:
    """rec: recsys.service.Recommender; case: hồ sơ người dùng (Case) hoặc None. -> list[Recommendation]."""
    from recsys.service import Recommendation

    w, b = rec.world, rec.builder
    i = rec.idx[paper_id]
    n = len(w.item_ids)
    mode = "w" if "w" in b.modes else "raw"

    blocked = np.ones(n, dtype=bool)
    blocked[w.pool] = False
    blocked[rec.not_candidate] = True
    blocked[i] = True
    if case is not None:
        blocked[case.known()] = True

    x = np.zeros((n, 1), dtype=np.float32)
    x[i] = 1
    cited_by_this = np.zeros(n, dtype=bool)
    cited_by_this[w.cites.get(i, np.array([], dtype=int))] = True
    cites_this = np.asarray(b.A["raw"][:, i].todense()).ravel() > 0
    authors = set(w.item_authors[i])
    shared = np.zeros(n, dtype=np.float32)
    for au in authors:
        np.add.at(shared, rec.author_items.get(au, []), 1)
    shared[i] = 0
    feats = {
        "sim": w.emb @ w.emb[i],
        "cocit_w": b.graph[mode].cocitation(x).ravel(),
        "coupling_w": b.graph[mode].coupling(x).ravel(),
        "direct": (cited_by_this | cites_this).astype(np.float32),
        "coauthor": shared,
    }

    picked = []
    for src, top in SOURCES.items():
        s = np.where(blocked, -np.inf, feats[src] if src == "sim" else np.where(feats[src] > 0, feats["sim"], -np.inf))
        top_idx = np.argpartition(-s, min(top, n - 1))[:top]
        picked.append(top_idx[np.isfinite(s[top_idx])])
    cand = np.unique(np.concatenate(picked))
    if len(cand) == 0:
        return []

    names = list(feats) + ["q"]
    cols = [feats[f][cand] for f in feats] + [np.nan_to_num(b.q[w.pool_pos[cand]], nan=0.0)]
    if case is not None:
        idx, pw = b.profile(case, mode)
        if len(idx):
            cent, pi = profile.cluster_profile(np.asarray(w.emb[idx], dtype=np.float32), pw)
            names.append("profile")
            cols.append(profile.multi_interest_scores(w.emb[cand], cent, pi))
    F = np.stack(cols, axis=1)[None].astype(np.float32)
    valid = np.ones((1, len(cand)), dtype=bool)
    Z = standardize(F, valid, names)[0]
    wv = np.array([RELATED_WEIGHTS[f] for f in names], dtype=np.float32)
    parts_all = Z * wv
    S = parts_all.sum(axis=1)

    order = np.argsort(-S)
    if diversity > 0 and len(order) > 1:
        top = order[:50]
        order = np.concatenate([top[mmr(S[top], w.emb[cand[top]], len(top), lam=1 - 0.5 * diversity)], order[50:]])

    out = []
    for j in order[:k]:
        item = int(cand[j])
        parts = {f: round(float(v), 3) for f, v in zip(names, parts_all[j])}
        reasons = []
        if cited_by_this[item]:
            reasons.append({"code": "cited_by_this", "params": {}})
        if cites_this[item]:
            reasons.append({"code": "cites_this", "params": {}})
        for f, v in sorted(parts.items(), key=lambda kv: -kv[1]):
            code = REASON_CODES.get(f)
            if v <= 0 or code is None:
                continue
            params = {}
            if code == "same_author":
                common = [a for a in w.item_authors[item] if a in authors]
                params = {"names": ", ".join(rec.author_name.get(a, a) for a in common[:2])}
            elif code == "similar_to_profile":
                params = rec.closest_profile_title(case, item)
            reasons.append({"code": code, "params": params})
        out.append(Recommendation(rec.paper_ids[item], float(S[j]), parts, reasons[:n_reasons]))
    return out
