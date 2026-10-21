"""arxiv_oai: đọc trang OAI-PMH và chọn bản ghi arXiv khớp với bài OpenReview."""
import unittest

from crawler.arxiv_oai import _parse_page, _pick

PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>
<record><header><identifier>oai:arXiv.org:2410.00001</identifier></header><metadata>
<arXiv xmlns="http://arxiv.org/OAI/arXiv/"><id>2410.00001</id>
<authors><author><keyname>M\xc3\xbcller</keyname><forenames>Anna</forenames></author></authors>
<title>Sharper Bounds for
  $\\ell_p$ Sensitivity Sampling</title><categories>cs.LG stat.ML</categories></arXiv></metadata></record>
<record><header status="deleted"><identifier>oai:arXiv.org:2410.00002</identifier></header></record>
<resumptionToken>skip=1300</resumptionToken></ListRecords></OAI-PMH>"""


def _rec(ax, *authors):
    return {"id": ax, "title": "T", "authors": list(authors), "categories": "cs.LG"}


class ParsePageTest(unittest.TestCase):
    def test_records_and_token(self):
        rows, token = _parse_page(PAGE)
        self.assertEqual(token, "skip=1300")
        self.assertEqual(len(rows), 1)          # bản ghi bị xoá không có metadata
        self.assertEqual(rows[0]["title"], "Sharper Bounds for $\\ell_p$ Sensitivity Sampling")
        self.assertEqual(rows[0]["authors"], ["Müller"])

    def test_no_records(self):
        page = b"""<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/">
                   <error code="noRecordsMatch">empty</error></OAI-PMH>"""
        self.assertEqual(_parse_page(page), ([], None))


class PickTest(unittest.TestCase):
    sub = {"authors": ["Anna Muller", "Bo Zhang"], "edition": 2025}

    def test_needs_author_overlap(self):
        self.assertIsNone(_pick(self.sub, [_rec("2410.00001", "Smith")]))
        self.assertEqual(_pick(self.sub, [_rec("2410.00001", "Müller")])["id"], "2410.00001")

    def test_too_old(self):
        self.assertIsNone(_pick(self.sub, [_rec("2001.00001", "Zhang")]))

    def test_prefers_overlap_then_earliest(self):
        cands = [_rec("2409.00002", "Zhang"), _rec("2410.00001", "Zhang", "Muller"), _rec("2408.00003", "Zhang")]
        self.assertEqual(_pick(self.sub, cands)["id"], "2410.00001")
        self.assertEqual(_pick(self.sub, cands[::2])["id"], "2408.00003")

    def test_no_authors_on_openreview(self):
        self.assertEqual(_pick({"authors": [], "edition": 2025}, [_rec("2410.00001", "Smith")])["id"], "2410.00001")


if __name__ == "__main__":
    unittest.main()
