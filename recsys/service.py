"""Gợi ý cho người dùng thật: cùng pipeline với đánh giá (recsys.pipeline), tại T = ngày mai.

1. Hồ sơ (Case): bài đã viết (OpenReview ID, trừ bài người dùng bỏ xác nhận, cộng bài tự thêm), bài các bài đó trích,
   bài đã lưu (0,7) và đã đọc (0,3) nhân time decay (spec 7.2).
2. Ứng viên + đặc trưng: FeatureBuilder, chỉ tính các chế độ cạnh mà mô hình dùng.
3. Xếp hạng: mô hình tuyến tính đã học (recsys.model), chỉnh theo sở thích khai báo (Tuning): thanh "Độ mới" đổi
   trọng số age / pop, bài thuộc lĩnh vực quan tâm hoặc khớp từ khoá được cộng điểm; rồi MMR theo thanh "Độ đa dạng".
   Bộ lọc cứng (API truyền vào `allowed`) và bài khớp sở thích (nguồn "pref") tác động ngay ở bước sinh ứng viên.
4. Giải thích: các đặc trưng đóng góp nhiều nhất (w_j · z_j) -> mã lý do cho giao diện.

Người dùng chưa có bài nào trong hồ sơ (cold-start) trả về None: API dùng gợi ý theo sở thích khai báo.
"""
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from recsys import profile, related
from recsys.model import LinearModel
from recsys.pipeline import FeatureBuilder, _decay
from recsys.ranking import linear_scores, standardize
from recsys.rerank import mmr
from recsys.snapshot import EDGE_FEATURES, Case, build_world

log = logging.getLogger(__name__)

MMR_POOL = 100
KEYWORD_CACHE = 64        # số bộ từ khoá giữ kết quả so khớp trên toàn kho
# Điểm cộng cho bài khớp sở thích khai báo, tính theo độ lệch chuẩn của điểm trong danh sách ứng viên của từng người
# (khoảng 2,6-3,0 trên dữ liệu thật) để tác động như nhau với hồ sơ đậm hay nhạt. Với Bengio + từ khoá "protein":
# 0,35 sd -> 3 bài khớp trong top 20, 1 sd -> 8 bài.
AREA_BONUS_SD = 1.0
KEYWORD_BONUS_SD = 1.0
PREF_CODES = ("area_match", "keyword_match")     # lý do theo sở thích khai báo luôn hiện trước
# Đặc trưng -> mã lý do hiển thị (frontend dịch); đặc trưng không có ở đây không dùng làm lời giải thích
REASON_CODES = {"rel_w": "similar_to_profile", "rel_raw": "similar_to_profile", "rel_mean": "similar_to_profile",
                "cocit_w": "cocited_with_yours", "cocit_raw": "cocited_with_yours",
                "coupling_w": "shares_references", "coupling_raw": "shares_references",
                "cites_me": "cites_you", "coauthor": "by_coauthor", "pop": "widely_cited", "q": "high_quality",
                "area": "area_match", "keyword": "keyword_match"}


@dataclass
class Recommendation:
    paper_id: str
    score: float
    parts: dict[str, float]                       # đóng góp w_j · z_j của từng đặc trưng
    reasons: list[dict] = field(default_factory=list)


@dataclass
class UserHistory:
    """Những gì API biết về người dùng (đọc từ Postgres)."""
    openreview_id: str | None = None
    not_mine: set[str] = field(default_factory=set)          # bài OpenReview gắn tên nhưng người dùng bỏ xác nhận
    manual_authored: set[str] = field(default_factory=set)   # bài tự thêm là của mình
    saved: dict[str, datetime] = field(default_factory=dict)
    read: dict[str, datetime] = field(default_factory=dict)
    hidden: set[str] = field(default_factory=set)            # không liên quan / đã đọc: không gợi ý lại


@dataclass
class Tuning:
    """Sở thích khai báo tác động lên thứ hạng (bộ lọc cứng như venue, năm do API áp sau)."""
    freshness: float = 0.5                                   # 0 = kinh điển, 0,5 = trọng số đã học, 1 = mới
    diversity: float = 0.0                                   # 0 = sát chủ đề, 1 = đa dạng (MMR)
    areas: set[str] = field(default_factory=set)             # primary_area quan tâm
    keywords: list[str] = field(default_factory=list)

    def weights(self, model: LinearModel) -> np.ndarray:
        """Độ mới f: age nhân 2f (0 -> bỏ age, 1 -> gấp đôi), pop nhân 1,5 - f (kinh điển thì bài được trích nhiều nặng hơn)."""
        w = model.w.copy()
        f = float(np.clip(self.freshness, 0.0, 1.0))
        for name, scale in (("age", 2 * f), ("pop", 1.5 - f)):
            if name in model.features:
                w[model.features.index(name)] *= scale
        return w


class Recommender:
    def __init__(self, catalog, model: LinearModel, today: date | None = None):
        """catalog: appdb.catalog.CatalogData."""
        today = today or date.today()
        self.T = str(today + timedelta(days=1))
        p = catalog.papers
        self.model = model
        self.paper_ids = p.id.to_numpy()
        self.idx = {pid: i for i, pid in enumerate(self.paper_ids)}
        self.titles = p.title.to_numpy()
        n = len(p)
        col = lambda c: p[c] if c in p else pd.Series([None] * n, index=p.index)
        self.areas = col("primary_area")
        kw = col("keywords").map(lambda k: " ".join(k) if isinstance(k, (list, tuple, np.ndarray)) else "")
        self.text = (p.title.fillna("") + " " + col("abstract").fillna("") + " " + kw).str.lower().to_numpy()
        self._kw_cache: OrderedDict[tuple[str, ...], np.ndarray] = OrderedDict()

        items = pd.DataFrame({"item_id": p.id, "first_seen": p.first_seen.fillna(p.decision_date)})
        pa = catalog.paper_authors
        self.author_name = dict(zip(pa.openreview_id, pa.name)) if "name" in pa else {}
        authors = pa.groupby("paper_id").openreview_id.apply(list).rename("authorids").reset_index() \
            .rename(columns={"paper_id": "item_id"})
        c = catalog.citations
        refs = pd.concat([
            pd.DataFrame({"citing_item": catalog.with_refs, "cited_item": None}),
            pd.DataFrame({"citing_item": c.citing_id, "cited_item": c.cited_id, **{k: c[k] for k in EDGE_FEATURES}}),
        ])
        self.world = build_world(self.T, items, authors, refs, catalog.emb)
        q = p.quality.to_numpy(dtype=float)
        self.builder = FeatureBuilder(self.world, q, modes=model.modes())
        self.cols = [self.builder.features.index(f) for f in model.features]
        self.not_candidate = np.flatnonzero(~p.is_candidate.to_numpy(dtype=bool))
        self.author_items: dict[str, list[int]] = {}
        for i, ids in enumerate(self.world.item_authors):
            for a in ids:
                self.author_items.setdefault(a, []).append(i)
        log.info("[recsys] sẵn sàng: %d bài, mô hình %s, T=%s", len(self.paper_ids), model.name, self.T)

    def case_for(self, h: UserHistory) -> Case | None:
        w = self.world
        authored = {i for i in self.author_items.get(h.openreview_id or "", [])
                    if self.paper_ids[i] not in h.not_mine}
        authored |= {self.idx[p] for p in h.manual_authored if p in self.idx}
        authored = np.array(sorted(authored), dtype=int)
        prior: dict[int, np.datetime64] = {}
        for i in authored:
            for r in w.cites.get(int(i), []):
                prior[int(r)] = max(prior.get(int(r), w.first_seen[i]), w.first_seen[i])
        t = np.datetime64(self.T)
        extra: dict[int, float] = {}
        for items, base in ((h.read, profile.W_READ), (h.saved, profile.W_SAVED)):
            for pid, when in items.items():
                if pid in self.idx:
                    d = float(_decay(t, [np.datetime64(when.date() if isinstance(when, datetime) else when, "D")])[0])
                    extra[self.idx[pid]] = max(extra.get(self.idx[pid], 0.0), base * d)
        if len(authored) == 0 and not extra:
            return None
        exclude = np.concatenate([self.not_candidate,
                                  np.array([self.idx[p] for p in h.hidden if p in self.idx], dtype=int)])
        first = np.array([w.item_authors[i][:1] == [h.openreview_id] for i in authored], dtype=bool)
        return Case(h.openreview_id or "", "user", authored, first, prior, np.array([], dtype=int),
                    extra=extra, exclude=exclude)

    def profile_items(self, h: UserHistory) -> list[tuple[str, list[str], float]]:
        """Các bài đang nằm trong hồ sơ, đúng như bộ gợi ý dùng: (paper_id, vai trò, trọng số), trọng số giảm dần.
        Vai trò: authored / cited / saved / read; trọng số đã gồm time decay và (với bài đã trích) w của cạnh."""
        case = self.case_for(h)
        if case is None:
            return []
        mode = "w" if "w" in self.builder.modes else "raw"
        idx, w = self.builder.profile(case, mode)
        roles: dict[int, list[str]] = {}
        for i in case.authored:
            roles.setdefault(int(i), []).append("authored")
        for i in case.prior:
            roles.setdefault(int(i), []).append("cited")
        for pid in h.saved:
            if pid in self.idx:
                roles.setdefault(self.idx[pid], []).append("saved")
        for pid in h.read:
            if pid in self.idx:
                roles.setdefault(self.idx[pid], []).append("read")
        weight = dict(zip(idx.tolist(), w.tolist()))
        # bài đã trích có w = 0 (bị bộ lọc cạnh bỏ) vẫn liệt kê, trọng số 0
        out = [(self.paper_ids[i], r, float(weight.get(i, 0.0))) for i, r in roles.items()]
        return sorted(out, key=lambda x: -x[2])

    def _keyword_mask(self, kws: tuple[str, ...]) -> np.ndarray:
        """Bài chứa ít nhất một từ khoá trong tiêu đề / abstract / keywords (như api/placeholder), có cache."""
        if kws not in self._kw_cache:
            self._kw_cache[kws] = np.fromiter((any(k in t for k in kws) for t in self.text), dtype=bool,
                                              count=len(self.text))
            if len(self._kw_cache) > KEYWORD_CACHE:
                self._kw_cache.popitem(last=False)
        self._kw_cache.move_to_end(kws)
        return self._kw_cache[kws]

    def preference_masks(self, tuning: Tuning) -> tuple[np.ndarray, np.ndarray]:
        """(thuộc lĩnh vực quan tâm, khớp từ khoá) theo từng bài trong catalog."""
        area = self.areas.isin(tuning.areas).to_numpy() if tuning.areas else np.zeros(len(self.text), dtype=bool)
        kws = tuple(sorted({k.strip().lower() for k in tuning.keywords if k.strip()}))
        kw = self._keyword_mask(kws) if kws else np.zeros(len(self.text), dtype=bool)
        return area, kw

    def recommend(self, h: UserHistory, tuning: Tuning | None = None, allowed: np.ndarray | None = None,
                  n_reasons: int = 2) -> list[Recommendation] | None:
        """allowed: bool theo thứ tự catalog.papers, chỉ gợi ý bài True (bộ lọc cứng của API); None = không lọc."""
        tuning = tuning or Tuning()
        case = self.case_for(h)
        if case is None:
            return None
        area_mask, kw_mask = self.preference_masks(tuning)
        case.allowed = allowed
        case.boost = (area_mask | kw_mask) if (tuning.areas or tuning.keywords) else None
        cache = self.builder.build([case])
        valid = cache.valid
        w = tuning.weights(self.model)
        Z = standardize(cache.F[..., self.cols], valid, self.model.features)
        items = self.world.pool[cache.cand[0]]
        area_hit = area_mask[items]
        kws = [k.strip().lower() for k in tuning.keywords if k.strip()]
        kw_hits = [[k for k in kws if k in self.text[i]] if kw_mask[i] else [] for i in items]
        S = linear_scores(Z, w, valid)[0]
        sd = float(S[np.isfinite(S)].std()) if np.isfinite(S).sum() > 1 else 1.0
        area_bonus, kw_bonus = AREA_BONUS_SD * sd, KEYWORD_BONUS_SD * sd
        S = S + area_bonus * area_hit + kw_bonus * np.array([bool(k) for k in kw_hits], dtype=float)
        order = np.argsort(-S)
        order = order[np.isfinite(S[order])]
        if tuning.diversity > 0 and len(order) > 1:
            top = order[:MMR_POOL]
            pos = cache.cand[0][top]
            chosen = top[mmr(S[top], self.builder.pool_emb[pos], len(top), lam=1 - 0.5 * tuning.diversity)]
            order = np.concatenate([chosen, order[MMR_POOL:]])

        parts_all = Z[0] * w
        out = []
        for j in order:
            item = int(items[j])
            parts = {f: round(float(v), 3) for f, v in zip(self.model.features, parts_all[j])}
            if area_hit[j]:
                parts["area"] = round(area_bonus, 3)
            if kw_hits[j]:
                parts["keyword"] = round(kw_bonus, 3)
            reasons = self._reasons(parts, item, case, kw_hits[j])[:n_reasons]
            out.append(Recommendation(self.paper_ids[item], float(S[j]), parts, reasons))
        return out

    def related(self, paper_id: str, h: UserHistory | None = None, k: int = 10,
                diversity: float = 0.3) -> list[Recommendation] | None:
        """Bài liên quan tới paper_id (recsys.related), cá nhân hoá theo hồ sơ nếu có. None nếu bài không có trong pool."""
        if paper_id not in self.idx or self.world.pool_pos[self.idx[paper_id]] < 0:
            return None
        case = self.case_for(h) if h is not None else None
        if case is None and h is not None and h.hidden:
            # chưa có hồ sơ nhưng đã ẩn vài bài: vẫn loại các bài đó
            case = Case("", "user", np.array([], dtype=int), np.array([], dtype=bool), {}, np.array([], dtype=int),
                        exclude=np.array([self.idx[p] for p in h.hidden if p in self.idx], dtype=int))
        return related.related(self, paper_id, case, k, diversity)

    def closest_profile_title(self, case: Case | None, item: int) -> dict:
        """{"title": bài trong hồ sơ gần item nhất} cho lý do "gần với bài X trong hồ sơ của bạn"."""
        if case is None:
            return {}
        prof = np.concatenate([case.authored, np.fromiter(case.extra, dtype=int, count=len(case.extra))]).astype(int)
        if len(prof) == 0:
            return {}
        sims = self.world.emb[prof] @ self.world.emb[item]
        return {"title": str(self.titles[prof[int(np.argmax(sims))]])}

    def _reasons(self, parts: dict[str, float], item: int, case: Case, kw_hits: list[str] = ()) -> list[dict]:
        """Đặc trưng đóng góp dương lớn nhất -> lý do; độ liên quan nội dung kèm tên bài gần nhất trong hồ sơ.
        Khớp lĩnh vực / từ khoá (người dùng tự khai báo) luôn đứng trước để họ thấy sở thích của mình có tác dụng."""
        reasons, seen = [], set()
        for f, v in sorted(parts.items(), key=lambda kv: -kv[1]):
            code = REASON_CODES.get(f)
            if v <= 0 or code is None or code in seen:
                continue
            seen.add(code)
            params = {}
            if code == "similar_to_profile":
                params = self.closest_profile_title(case, item)
            elif code == "area_match":
                params = {"area": str(self.areas.iat[item])}          # API đổi sang nhãn hiển thị
            elif code == "keyword_match":
                params = {"keywords": ", ".join(kw_hits[:3])}
            reasons.append({"code": code, "params": params})
        return sorted(reasons, key=lambda r: r["code"] not in PREF_CODES)
