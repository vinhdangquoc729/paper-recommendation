"""Bộ gợi ý cho người dùng thật (recsys.service) trên catalog nhỏ dựng tay, và băm mật khẩu. Không cần Postgres."""
import unittest
from datetime import date, datetime

import numpy as np
import pandas as pd

from api.placeholder import recommend_filter
from api.schemas import Preferences
from api.userstore import check_password, hash_password
from appdb.catalog import CatalogData
from recsys.model import LinearModel
from recsys.service import Recommender, Tuning, UserHistory


def _catalog() -> CatalogData:
    # 3 chủ đề (trục 0, 1, 2); "mine" của ~A thuộc chủ đề 0 và trích "c0"
    ids = ["mine", "c0", "t0a", "t0b", "t1a", "t1b", "t2a", "wd"]
    axis = [0, 0, 0, 0, 1, 1, 2, 0]
    emb = np.zeros((len(ids), 768), dtype=np.float32)
    for i, a in enumerate(axis):
        emb[i, a] = 1.0
        emb[i, 10 + i] = 0.1          # mỗi bài khác nhau một chút
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    papers = pd.DataFrame({
        "id": ids, "title": [f"Paper {x}" for x in ids], "first_seen": ["2024-01-01"] * len(ids),
        "decision_date": [None] * len(ids), "quality": [0.5] * len(ids),
        "is_candidate": [True] * (len(ids) - 1) + [False],      # "wd": withdrawn, không gợi ý
        "primary_area": [f"area{a}" for a in axis], "abstract": [""] * len(ids),
        "keywords": [["graph"] if x == "t2a" else [] for x in ids],
    })
    pa = pd.DataFrame({"paper_id": ["mine", "t0a"], "openreview_id": ["~A", "~B"], "name": ["A", "B"],
                       "position": [0, 0]})
    cit = pd.DataFrame({"citing_id": ["mine", "t1a"], "cited_id": ["c0", "c0"], "has_cite_info": [1, 1],
                        "n_mentions": [2, 1], "in_method": [1, 0], "in_experiment": [0, 0], "only_in_list": [0, 0],
                        "appendix_only": [0, 0]})
    return CatalogData("v1", papers, emb, pd.DataFrame(), pa, cit, np.array(["mine", "t1a"]))


MODEL = LinearModel("test", ["rel_w", "pop"], [1.0, 0.0])


class RecommenderTest(unittest.TestCase):
    def setUp(self):
        self.rec = Recommender(_catalog(), MODEL, today=date(2026, 1, 1))

    def ids(self, recs):
        return [r.paper_id for r in recs]

    def test_cold_start_returns_none(self):
        self.assertIsNone(self.rec.recommend(UserHistory()))
        self.assertIsNone(self.rec.recommend(UserHistory(openreview_id="~Nobody")))

    def test_author_profile_ranks_own_topic_first_and_skips_known(self):
        out = self.ids(self.rec.recommend(UserHistory(openreview_id="~A")))
        self.assertNotIn("mine", out)     # đã viết
        self.assertNotIn("c0", out)       # đã trích
        self.assertNotIn("wd", out)       # không phải ứng viên
        self.assertEqual(set(out[:2]), {"t0a", "t0b"})

    def test_saved_papers_build_profile_and_hidden_are_excluded(self):
        h = UserHistory(saved={"t1a": datetime(2025, 12, 1)}, hidden={"t1b"})
        out = self.ids(self.rec.recommend(h))
        self.assertNotIn("t1a", out)
        self.assertNotIn("t1b", out)

    def test_not_mine_removes_paper_from_profile(self):
        self.assertIsNone(self.rec.recommend(UserHistory(openreview_id="~A", not_mine={"mine"})))

    def test_reasons_name_closest_profile_paper(self):
        top = self.rec.recommend(UserHistory(openreview_id="~A"))[0]
        self.assertEqual(top.reasons[0], {"code": "similar_to_profile", "params": {"title": "Paper mine"}})

    def test_freshness_scales_age_and_pop(self):
        m = LinearModel("m", ["rel_w", "pop", "age"], [1.0, 2.0, -1.5])
        np.testing.assert_allclose(Tuning(freshness=0.5).weights(m), [1.0, 2.0, -1.5])
        np.testing.assert_allclose(Tuning(freshness=0.0).weights(m), [1.0, 3.0, 0.0])
        np.testing.assert_allclose(Tuning(freshness=1.0).weights(m), [1.0, 1.0, -3.0])

    def test_area_and_keyword_add_bonus_and_reason(self):
        h = UserHistory(openreview_id="~A")
        base = {r.paper_id: r for r in self.rec.recommend(h)}
        tuned = {r.paper_id: r for r in self.rec.recommend(h, Tuning(areas={"area1"}, keywords=["Graph"]))}
        bonus = tuned["t1a"].parts["area"]
        self.assertGreater(bonus, 0)
        self.assertAlmostEqual(tuned["t1a"].score - base["t1a"].score, bonus, places=2)
        self.assertEqual(tuned["t1a"].reasons[0], {"code": "area_match", "params": {"area": "area1"}})
        self.assertIn({"code": "keyword_match", "params": {"keywords": "graph"}}, tuned["t2a"].reasons)
        self.assertAlmostEqual(tuned["t0a"].score, base["t0a"].score, places=4)

    def test_allowed_mask_limits_candidates(self):
        allowed = np.isin(self.rec.paper_ids, ["t1a", "t2a"])
        out = self.ids(self.rec.recommend(UserHistory(openreview_id="~A"), allowed=allowed))
        self.assertEqual(set(out), {"t1a", "t2a"})

    def test_pref_source_adds_matching_papers_to_candidates(self):
        case = self.rec.case_for(UserHistory(openreview_id="~A"))
        pool_ids = lambda cache: {self.rec.paper_ids[self.rec.world.pool[c]] for c in cache.cand[0] if c >= 0}
        only_rel = pool_ids(self.rec.builder.build([case], sources={"rel_raw": 1}))
        self.assertNotIn("t2a", only_rel)
        case.boost = np.isin(self.rec.paper_ids, ["t2a"])
        self.assertIn("t2a", pool_ids(self.rec.builder.build([case], sources={"rel_raw": 1})))

    def test_related_puts_cited_paper_first_with_reason(self):
        out = self.rec.related("mine")
        self.assertEqual(out[0].paper_id, "c0")                       # cùng chủ đề và được bài này trích
        self.assertEqual(out[0].reasons[0], {"code": "cited_by_this", "params": {}})
        self.assertNotIn("wd", [r.paper_id for r in out])

    def test_related_skips_papers_the_user_knows(self):
        ids = [r.paper_id for r in self.rec.related("t0a", UserHistory(openreview_id="~A"))]
        self.assertNotIn("mine", ids)     # đã viết
        self.assertNotIn("c0", ids)       # đã trích
        self.assertIn("t0b", ids)


class RecommendFilterTest(unittest.TestCase):
    df = pd.DataFrame({"venue_key": ["iclr", "icml", "iclr"], "edition": [2024, 2025, 2025],
                       "decision": ["accept_poster", "reject", "reject"], "code_url": [None, "x", None]})

    def test_preferences_apply_when_page_has_no_filter(self):
        mask = recommend_filter(self.df, Preferences(venues=["iclr"]), None, None, None, None)
        self.assertEqual(mask.tolist(), [True, False, False])          # mặc định chỉ bài được nhận

    def test_page_filter_overrides_conflicting_preference(self):
        prefs = Preferences(venues=["iclr"], year_from=2025)
        mask = recommend_filter(self.df, prefs, "icml", 2025, "reject", None)
        self.assertEqual(mask.tolist(), [False, True, False])
        mask = recommend_filter(self.df, Preferences(only_with_code=True, include_rejected=True), None, None, None, None)
        self.assertEqual(mask.tolist(), [False, True, False])


class PasswordTest(unittest.TestCase):
    def test_roundtrip(self):
        h = hash_password("matkhau123")
        self.assertTrue(check_password("matkhau123", h))
        self.assertFalse(check_password("sai", h))
        self.assertNotEqual(h, hash_password("matkhau123"))   # có salt
        self.assertFalse(check_password("x", None))


if __name__ == "__main__":
    unittest.main()
