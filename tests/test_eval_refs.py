import sqlite3
import unittest

from crawler.arxiv_ids import _ARXIV_ABS, MIN_SIMILARITY, title_match
from crawler.eval_targets import select_targets


class TestTitleMatch(unittest.TestCase):
    def test_exact_after_normalisation(self):
        self.assertEqual(title_match("Attention Is All You Need!", "attention is all you need"), 1.0)

    def test_different_titles_rejected(self):
        self.assertLess(title_match("Attention Is All You Need", "Attention Is Not All You Need"), MIN_SIMILARITY)

    def test_arxiv_abs_url(self):
        self.assertEqual(_ARXIV_ABS.search("http://arxiv.org/abs/2410.01234v2").group(1), "2410.01234")


class TestSelectTargets(unittest.TestCase):
    def _db(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("""CREATE TABLE or_submissions (forum_id TEXT, title TEXT, title_norm TEXT, authorids TEXT,
                        odate TEXT, pdate TEXT, cdate TEXT)""")
        rows = [  # tác giả ~A: 2 bài trước T, 1 bài sau T (nộp 2 lần) -> đủ điều kiện; ~B: chỉ 1 bài trước
            ("f1", "a long enough first paper title", '["~A"]', "2024-01-01"),
            ("f2", "a long enough second paper title", '["~A", "~B"]', "2024-05-01"),
            ("f3", "a long enough third paper title", '["~A"]', "2025-03-01"),
            ("f4", "a long enough third paper title", '["~A"]', "2025-06-01"),
        ]
        conn.executemany("INSERT INTO or_submissions VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                         [(f, t, t.replace(" ", ""), a, d) for f, t, a, d in rows])
        return conn

    def test_eligibility_and_resubmissions_merged(self):
        authors, target = select_targets(self._db(), "2025-01-01", n_authors=10, seed=0)
        self.assertEqual(list(authors), ["~A"])
        self.assertEqual(len(target), 1)
        self.assertEqual(sorted(target.iloc[0].forums), ["f3", "f4"])


if __name__ == "__main__":
    unittest.main()
