"""Giao thức đánh giá: cắt theo T, ground truth, loại bài đã biết, độ đo."""
import unittest

import numpy as np
import pandas as pd

from eval import metrics, run
from eval.baselines import ContentMean, Popularity
from eval.protocol import build_cases, build_world, split_of

T = "2025-01-01"


def _world(c3_authors=("~Y",)):
    # bài: o1, o2 cũ của A; c1..c4 bài khác trước T; n1 bài A viết sau T (đứng đầu); n2 bài A viết sau T (ở giữa)
    # late: bài người khác công khai sau T
    items = pd.DataFrame({"item_id": ["o1", "o2", "c1", "c2", "c3", "c4", "mine", "n1", "n2", "late"],
                          "first_seen": ["2023-01-01", "2024-01-01", "2023-05-01", "2023-06-01", "2024-02-01",
                                         "2024-03-01", "2024-04-01", "2025-03-01", "2025-04-01", "2025-02-01"]})
    authors = pd.DataFrame({"item_id": ["o1", "o2", "c1", "c2", "c3", "c4", "mine", "n1", "n2", "late"],
                            "authorids": [["~A"], ["~B", "~A"], ["~X"], ["~X"], list(c3_authors), ["~Y"], ["~A", "~Z"],
                                          ["~A", "~Q"], ["~Q", "~A", "~R"], ["~X"]]})
    refs = pd.DataFrame({"citing_item": ["o1", "o2", "n1", "n1", "n1", "n2", "c3", "c4"],
                         "cited_item": ["c1", "c1", "c1", "c2", "mine", "c3", "c1", "c1"]})
    refs = pd.concat([refs, pd.DataFrame({"citing_item": ["n2"], "cited_item": ["late"]})])
    emb = np.eye(10, dtype=np.float32)
    return build_world(T, items, authors, refs, emb)


class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.w = _world()
        self.ids = list(self.w.item_ids)

    def name(self, idx):
        return sorted(self.ids[i] for i in idx)

    def test_pool_is_before_T(self):
        self.assertEqual(self.name(self.w.pool), ["c1", "c2", "c3", "c4", "mine", "o1", "o2"])

    def test_in_degree_counts_only_citing_before_T(self):
        deg = dict(zip(self.ids, self.w.in_degree))
        self.assertEqual(deg["c1"], 4)   # o1, o2, c3, c4; n1 sau T không tính
        self.assertEqual(deg["c2"], 0)

    def test_ground_truth(self):
        (a,) = [c for c in build_cases(self.w) if c.author == "~A"]
        self.assertEqual(self.name(a.authored), ["mine", "o1", "o2"])
        self.assertEqual(self.name(a.prior), ["c1"])
        # c1 đã trích trước T, mine là bài của A, late công khai sau T: chỉ còn c2 (từ n1) và c3 (từ n2)
        self.assertEqual(self.name(a.gt), ["c2", "c3"])
        self.assertEqual((a.n_after, a.n_after_refs), (2, 2))

    def test_novel_variant_drops_papers_by_earlier_coauthors(self):
        # c3 có Z, người viết chung "mine" với A trước T: A gần như chắc chắn đã biết bài này
        w = _world(c3_authors=("~Y", "~Z"))
        (a,) = [c for c in build_cases(w, "novel") if c.author == "~A"]
        self.assertEqual(sorted(w.item_ids[i] for i in a.gt), ["c2"])
        (a,) = [c for c in build_cases(w, "all") if c.author == "~A"]
        self.assertEqual(sorted(w.item_ids[i] for i in a.gt), ["c2", "c3"])

    def test_lead_variant_drops_middle_author_papers(self):
        (a,) = [c for c in build_cases(self.w, "lead") if c.author == "~A"]
        self.assertEqual(self.name(a.gt), ["c2"])   # n2: A đứng giữa

    def test_grades_from_citation_context(self):
        w = self.w
        e = w.edges
        feats = pd.DataFrame({"has_cite_info": 1, "n_mentions": 1, "in_method": 0, "in_experiment": 0,
                              "only_in_list": 0, "appendix_only": 0}, index=e.index)
        pair = list(zip(e.a.map(lambda i: self.ids[i]), e.b.map(lambda i: self.ids[i])))
        feats.loc[[p == ("n1", "c2") for p in pair], "only_in_list"] = 1                  # trích cho có
        feats.loc[[p == ("n2", "c3") for p in pair], ["n_mentions", "in_method"]] = [3, 1]  # trích mạnh
        refs = pd.DataFrame({"citing_item": [self.ids[i] for i in e.a], "cited_item": [self.ids[i] for i in e.b],
                             **{c: feats[c].to_numpy() for c in feats}})
        items = pd.DataFrame({"item_id": self.ids, "first_seen": w.first_seen.astype(str)})
        authors = pd.DataFrame({"item_id": self.ids, "authorids": w.item_authors})
        (a,) = [c for c in build_cases(build_world(T, items, authors, refs)) if c.author == "~A"]
        self.assertEqual(dict(zip(self.name(a.gt), a.grade.tolist())), {"c2": 0, "c3": 3})

    def test_authors_without_history_excluded(self):
        self.assertEqual([c.author for c in build_cases(self.w)], ["~A"])

    def test_split_is_stable_and_balanced(self):
        self.assertEqual(split_of("~A"), split_of("~A"))
        counts = pd.Series([split_of(f"~P{i}") for i in range(5000)]).value_counts(normalize=True)
        self.assertAlmostEqual(counts["train"], 0.6, delta=0.03)
        self.assertAlmostEqual(counts["test"], 0.2, delta=0.03)

    def test_evaluate_never_recommends_known_items(self):
        cases = build_cases(self.w)
        for method in (Popularity(), ContentMean(self.w)):
            _, tops = run.evaluate(self.w, cases, method)
            self.assertEqual(self.name(tops[0]), ["c2", "c3", "c4"])   # pool trừ bài đã viết, đã trích


class MetricsTest(unittest.TestCase):
    def test_recall_ndcg(self):
        hits = np.array([False, True, False, True])
        self.assertAlmostEqual(metrics.recall_at_k(hits, 4, 4), 0.5)
        ideal = 1 + 1 / np.log2(3)
        self.assertAlmostEqual(metrics.ndcg_at_k(hits, 2, 4), (1 / np.log2(3) + 1 / np.log2(5)) / ideal)
        self.assertAlmostEqual(metrics.ndcg_at_k(np.array([True, True]), 2, 10), 1.0)

    def test_ndcg_graded(self):
        self.assertAlmostEqual(metrics.ndcg_graded(np.array([3, 1]), np.array([1, 3]), 10), 1.0)
        self.assertLess(metrics.ndcg_graded(np.array([1, 3]), np.array([1, 3]), 10), 1.0)
        self.assertTrue(np.isnan(metrics.ndcg_graded(np.array([0]), np.array([0, 0]), 10)))

    def test_intra_list_distance(self):
        self.assertAlmostEqual(metrics.intra_list_distance(np.eye(3)), 1.0)
        self.assertAlmostEqual(metrics.intra_list_distance(np.ones((3, 1))), 0.0)

    def test_paired_diff(self):
        a = np.zeros(50)
        r = metrics.paired_diff(a, a + 0.1)
        self.assertAlmostEqual(r["diff"], 0.1)
        self.assertLess(r["p"], 0.01)


if __name__ == "__main__":
    unittest.main()
