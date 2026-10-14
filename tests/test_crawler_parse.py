import unittest

from crawler.parse import (authors_visible, edition_from_dblp, norm_title, normalize_decision,
                           parse_number, parse_submission)


class TestParse(unittest.TestCase):
    def test_edition_from_dblp(self):
        self.assertEqual(edition_from_dblp("conf/iclr/HuangCQ24", "conf/iclr/"), 2024)
        self.assertEqual(edition_from_dblp("conf/nips/WangLL24a", "conf/nips/"), 2024)
        self.assertIsNone(edition_from_dblp("journals/corr/abs-2410-03618", "conf/iclr/"))
        self.assertIsNone(edition_from_dblp(None, "conf/iclr/"))

    def test_parse_number(self):
        self.assertEqual(parse_number("6: marginally above the acceptance threshold"), 6.0)
        self.assertEqual(parse_number(8), 8.0)
        self.assertIsNone(parse_number("Accept"))
        self.assertIsNone(parse_number(None))

    def test_normalize_decision(self):
        self.assertEqual(normalize_decision("Accept: notable-top-5%"), "accept_oral")
        self.assertEqual(normalize_decision("Accept: notable-top-25%"), "accept_spotlight")
        self.assertEqual(normalize_decision("Accept (poster)"), "accept_poster")
        self.assertEqual(normalize_decision("Reject"), "reject")
        self.assertEqual(normalize_decision(None, "ICLR.cc/2024/Conference/Withdrawn_Submission"), "withdrawn")
        self.assertEqual(normalize_decision(None, "Submitted to ICLR 2024", "ICLR.cc/2024/Conference"), None)
        self.assertEqual(normalize_decision("Accept as is"), "accept")

    def test_authors_visible(self):
        self.assertTrue(authors_visible(["~Nguyen_Van_A1"]))
        self.assertFalse(authors_visible(["ICLR.cc/2023/Conference/Paper1/Authors"]))
        self.assertFalse(authors_visible(None))

    def test_norm_title(self):
        self.assertEqual(norm_title("Attention Is All You Need!"), norm_title("attention is all you need"))

    def test_parse_submission_v2(self):
        note = {
            "id": "abc", "number": 1, "cdate": 1695000000000, "odate": 1696000000000,
            "content": {
                "title": {"value": "A Paper"}, "abstract": {"value": "x"},
                "authorids": {"value": ["~A_B1"]}, "venue": {"value": "ICLR 2024 spotlight"},
                "venueid": {"value": "ICLR.cc/2024/Conference"},
            },
            "details": {"directReplies": [
                {"id": "r1", "invitations": ["ICLR.cc/2024/Conference/Submission1/-/Official_Review"],
                 "content": {"rating": {"value": "8: accept, good paper"}, "confidence": {"value": "4: confident"}}},
                {"id": "d1", "invitations": ["ICLR.cc/2024/Conference/Submission1/-/Decision"],
                 "content": {"decision": {"value": "Accept (spotlight)"}}},
            ]},
        }
        row, reviews = parse_submission(note)
        self.assertEqual(row["decision"], "accept_spotlight")
        self.assertEqual(row["authorids"], ["~A_B1"])
        self.assertEqual(reviews[0]["rating"], 8.0)
        self.assertEqual(reviews[0]["confidence"], 4.0)

    def test_parse_submission_icml_overall_recommendation(self):
        note = {
            "id": "i", "content": {"title": {"value": "C"}, "venue": {"value": "ICML 2025 poster"}},
            "details": {"directReplies": [
                {"id": "r", "invitations": ["ICML.cc/2025/Conference/Submission5/-/Official_Review"],
                 "content": {"overall_recommendation": {"value": "4: Accept"}}},
            ]},
        }
        row, reviews = parse_submission(note)
        self.assertEqual(reviews[0]["rating"], 4.0)
        self.assertEqual(row["decision"], "accept_poster")

    def test_parse_submission_v1_anonymous(self):
        note = {
            "id": "xyz", "cdate": 1664000000000,
            "content": {"title": "B", "authorids": ["ICLR.cc/2023/Conference/Paper9/Authors"],
                        "venue": "ICLR 2023 poster"},
            "details": {"directReplies": [
                {"id": "r", "invitation": "ICLR.cc/2023/Conference/Paper9/-/Official_Review",
                 "content": {"recommendation": "6: marginally above the acceptance threshold"}},
            ]},
        }
        row, reviews = parse_submission(note)
        self.assertEqual(row["authorids"], [])
        self.assertEqual(row["decision"], "accept_poster")
        self.assertEqual(reviews[0]["rating"], 6.0)


if __name__ == "__main__":
    unittest.main()


class TestParseExtraFields(unittest.TestCase):
    def test_area_code_and_dates(self):
        note = {
            "id": "f1", "content": {
                "title": "T", "authorids": ["~A1"], "authors": ["A"],
                "Please_choose_the_closest_area_that_your_submission_falls_into": "Deep Learning",
                "code": "Code: https://github.com/x/y.",
            },
            "details": {"directReplies": [
                {"id": "r", "invitation": "ICLR.cc/2023/Conference/Paper1/-/Official_Review",
                 "cdate": 1668000000000, "content": {"recommendation": "8: accept"}},
                {"id": "d", "invitation": "ICLR.cc/2023/Conference/Paper1/-/Decision",
                 "cdate": 1674000000000, "content": {"decision": "Reject"}},
            ]},
        }
        row, reviews = parse_submission(note)
        self.assertEqual(row["primary_area"], "Deep Learning")
        self.assertEqual(row["code_url"], "https://github.com/x/y")
        self.assertEqual(row["decision_date"], "2023-01-18")
        self.assertEqual(reviews[0]["cdate"], "2022-11-09")

    def test_code_url_placeholder_ignored(self):
        row, _ = parse_submission({"id": "f", "content": {"link_to_code": {"value": "N/A"}}})
        self.assertIsNone(row["code_url"])
