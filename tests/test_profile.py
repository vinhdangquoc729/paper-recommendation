"""Hồ sơ đa sở thích: phân cụm có trọng số và điểm rel_max."""
import unittest

import numpy as np

from recsys import profile


def _two_topics(n_a=8, n_b=2, seed=0):
    rng = np.random.default_rng(seed)
    a, b = np.zeros(16), np.zeros(16)
    a[0], b[1] = 1, 1
    vecs = np.vstack([a + 0.05 * rng.standard_normal((n_a, 16)), b + 0.05 * rng.standard_normal((n_b, 16))])
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


class ProfileTest(unittest.TestCase):
    def test_n_clusters(self):
        self.assertEqual(profile.n_clusters(1), 1)
        self.assertEqual(profile.n_clusters(11), 3)
        self.assertEqual(profile.n_clusters(100), 5)

    def test_clusters_separate_topics_and_weigh_them(self):
        vecs = _two_topics()
        cent, pi = profile.cluster_profile(vecs, np.ones(len(vecs)), k=2)
        self.assertEqual(len(cent), 2)
        big = int(np.argmax(pi))
        self.assertAlmostEqual(pi[big], 0.8)
        self.assertGreater(cent[big, 0], 0.95)
        self.assertGreater(cent[1 - big, 1], 0.95)

    def test_minor_interest_still_scores_high(self):
        vecs = _two_topics()
        cent, pi = profile.cluster_profile(vecs, np.ones(len(vecs)), k=2)
        cand = np.eye(16)[:3]                             # chủ đề chính, chủ đề phụ, chủ đề lạ
        rel = profile.multi_interest_scores(cand, cent, pi)
        mean = cand @ profile.mean_profile(vecs, np.ones(len(vecs)))
        self.assertGreater(rel[1], 0.45)                  # cụm nhỏ vẫn được ít nhất floor 0,5
        self.assertGreater(rel[1], mean[1])               # vector trung bình làm nhoè chủ đề phụ
        self.assertLess(rel[2], 0.1)

    def test_duplicate_points_do_not_crash(self):
        vecs = np.tile(np.eye(4)[0], (6, 1))
        cent, pi = profile.cluster_profile(vecs, np.ones(6), k=3)
        self.assertAlmostEqual(pi.sum(), 1.0)
        self.assertEqual(len(cent), 1)


if __name__ == "__main__":
    unittest.main()
