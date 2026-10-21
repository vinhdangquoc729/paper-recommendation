"""Trọng số cạnh (V3), láng giềng đồ thị, chuẩn hoá đặc trưng, MMR."""
import unittest

import numpy as np
import pandas as pd

from features import reference_filter as rf
from recsys import ranking, rerank
from recsys.graph import GraphScorer, citation_matrix


def _edges(**cols):
    base = dict(b=[0, 1], has_cite_info=[1, 1], n_mentions=[1, 1], in_method=[0, 0], in_experiment=[0, 0],
                only_in_list=[0, 0], appendix_only=[0, 0])
    return pd.DataFrame(base | cols)


class EdgeWeightTest(unittest.TestCase):
    def test_context_rewards_mentions_and_method(self):
        e = _edges(n_mentions=[5, 1], in_method=[1, 0])
        ctx = rf.context_score(e, np.array([0.8, 0.8]))
        self.assertGreater(ctx[0], ctx[1])

    def test_context_penalizes_long_cite_lists_and_appendix(self):
        for col in ("only_in_list", "appendix_only"):
            ctx = rf.context_score(_edges(**{col: [1, 0]}), np.array([0.8, 0.8]))
            self.assertLess(ctx[0], ctx[1])

    def test_missing_cite_info_ignores_flags(self):
        e = _edges(has_cite_info=[0, 1], only_in_list=[1, 1])
        ctx = rf.context_score(e, np.array([0.8, 0.8]))
        self.assertGreater(ctx[0], ctx[1])

    def test_idf_down_weights_hubs(self):
        w = rf.edge_weights(_edges(), np.array([0.8, 0.8]), deg_in=np.array([500, 2]), n_citing=1000, mode="idf")
        self.assertLess(w[0], w[1])

    def test_modes(self):
        e, sim, deg = _edges(), np.array([0.5, 0.9]), np.array([900, 1])
        self.assertTrue(np.all(rf.edge_weights(e, sim, deg, 1000, "raw") == 1))
        w = rf.edge_weights(e, sim, deg, 1000, "w")
        wt = rf.edge_weights(e, sim, deg, 1000, "w_theta")
        self.assertTrue(np.all((wt == 0) | (wt == w)))
        self.assertEqual(wt[0], 0)   # hub, ít giống nội dung: bị bỏ


class GraphTest(unittest.TestCase):
    def setUp(self):
        # bài 0, 1 cùng trích 3 và 4; bài 2 trích 4 và 5
        citing = np.array([0, 0, 1, 1, 2, 2])
        cited = np.array([3, 4, 3, 4, 4, 5])
        self.g = GraphScorer(citation_matrix(citing, cited, np.ones(6), 6))

    def test_cocitation(self):
        x = np.zeros((6, 1))
        x[3] = 1
        s = self.g.cocitation(x).ravel()
        self.assertGreater(s[4], s[5])         # 4 được trích cùng 3 hai lần, 5 thì không
        self.assertEqual(s[5], 0)

    def test_coupling(self):
        x = np.zeros((6, 1))
        x[0] = 1
        s = self.g.coupling(x).ravel()
        self.assertAlmostEqual(s[1], 1.0)      # cùng danh sách reference
        self.assertAlmostEqual(s[2], 0.5)      # chung một trong hai

    def test_zero_weight_edges_dropped(self):
        A = citation_matrix(np.array([0, 1]), np.array([2, 2]), np.array([0.0, 1.0]), 3)
        self.assertEqual(A.nnz, 1)


class RankingTest(unittest.TestCase):
    def test_standardize_per_user_and_mask(self):
        F = np.array([[[1.0, 0], [3.0, 10], [99, 99]]])
        valid = np.array([[True, True, False]])
        Z = ranking.standardize(F, valid, ["rel", "cocit_w"])
        np.testing.assert_allclose(Z[0, :2, 0], [-1, 1], atol=1e-6)
        self.assertEqual(Z[0, 2].tolist(), [0, 0])
        S = ranking.linear_scores(Z, np.array([1.0, 0.0]), valid)
        self.assertEqual(S[0, 2], -np.inf)


class MMRTest(unittest.TestCase):
    def test_lambda_one_keeps_order_lambda_low_diversifies(self):
        emb = np.array([[1, 0], [1, 0], [0, 1]], dtype=float)
        scores = np.array([1.0, 0.9, 0.5])
        self.assertEqual(rerank.mmr(scores, emb, 3, lam=1.0).tolist(), [0, 1, 2])
        self.assertEqual(rerank.mmr(scores, emb, 2, lam=0.3).tolist(), [0, 2])   # bài trùng nội dung bị đẩy xuống


if __name__ == "__main__":
    unittest.main()
