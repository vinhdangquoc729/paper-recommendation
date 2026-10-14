import unittest

import pandas as pd

from features.items import build_items
from features.quality import compute_quality

TITLE = "a reasonably long paper title for testing"


def _sub(forum_id, venue, edition, decision, title=TITLE, odate="2024-01-01", decision_date=None, **kw):
    row = dict(forum_id=forum_id, venue_key=venue, edition=edition, title=title,
               title_norm=title.replace(" ", ""), abstract="abs", tldr=None, keywords="[]", primary_area=None,
               code_url=None, authors="[]", authorids="[]", decision=decision, decision_date=decision_date,
               cdate=odate, odate=odate, pdate=None, n_reviews=0)
    return row | kw


class TestItems(unittest.TestCase):
    def test_resubmission_merged_into_accepted_version(self):
        subs = pd.DataFrame([
            _sub("r1", "iclr", 2024, "reject", odate="2023-10-01"),
            _sub("a1", "icml", 2024, "accept_poster", odate="2024-06-01"),
            _sub("x", "iclr", 2024, "reject", title="another long and distinct title"),
        ])
        items, versions = build_items(subs)
        self.assertEqual(sorted(items.item_id), ["a1", "x"])
        merged = items.set_index("item_id").loc["a1"]
        self.assertEqual(merged.n_versions, 2)
        self.assertEqual(merged.first_seen, "2023-10-01")   # bài đã công khai từ lần nộp ICLR
        self.assertEqual(versions.set_index("forum_id").item_id["r1"], "a1")

    def test_short_titles_not_merged(self):
        subs = pd.DataFrame([_sub("a", "iclr", 2024, "reject", title="Untitled"),
                             _sub("b", "iclr", 2025, "reject", title="Untitled")])
        self.assertEqual(len(build_items(subs)[0]), 2)

    def test_withdrawn_is_not_candidate(self):
        items, _ = build_items(pd.DataFrame([_sub("w", "iclr", 2024, "withdrawn")]))
        self.assertEqual(items.is_candidate.iloc[0], 0)


def _quality_fixture():
    # 40 bài ICLR 2024, mỗi bài 1 review; bài p0 điểm cao nhất
    subs = [_sub(f"p{i}", "iclr", 2024, "accept_poster" if i < 20 else "reject",
                 title=f"paper number {i} with a long enough title", decision_date="2024-01-15")
            for i in range(40)]
    reviews = pd.DataFrame([dict(forum_id=f"p{i}", rating=10 - i / 5, confidence=3.0, cdate="2023-11-01")
                            for i in range(40)])
    items, versions = build_items(pd.DataFrame(subs))
    return items, versions, reviews


class TestQuality(unittest.TestCase):
    def test_better_reviews_and_decision_give_higher_q(self):
        q = compute_quality(*_quality_fixture()).set_index("item_id").q
        self.assertGreater(q["p0"], q["p19"])
        self.assertGreater(q["p19"], q["p39"])
        self.assertTrue(((q >= 0) & (q <= 1)).all())

    def test_as_of_hides_future_reviews_and_decisions(self):
        q = compute_quality(*_quality_fixture(), as_of="2023-10-15").set_index("item_id")
        self.assertTrue((q.n_ratings == 0).all())
        self.assertTrue((q.decision_known == 0).all())
        q = compute_quality(*_quality_fixture(), as_of="2023-12-01").set_index("item_id")
        self.assertTrue((q.n_ratings == 1).all())       # review ICLR đã công khai
        self.assertTrue((q.decision_known == 0).all())  # decision thì chưa

    def test_closed_venue_reviews_visible_only_after_decision(self):
        items, versions, reviews = _quality_fixture()
        versions = versions.assign(venue_key="neurips")
        q = compute_quality(items, versions, reviews, as_of="2023-12-01")
        self.assertTrue((q.n_ratings == 0).all())


if __name__ == "__main__":
    unittest.main()
