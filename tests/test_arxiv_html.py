"""Đọc reference và trích dẫn từ bản HTML (LaTeXML) của arXiv."""
import unittest

from crawler.arxiv_html import is_latexml, parse_html
from crawler.latex import citation_features

PAGE = """<!DOCTYPE html><html><head><title>T</title><style>.x{}</style></head><body>
<div class="ltx_page_main"><article class="ltx_document">
<div class="ltx_abstract"><p>We build on <cite class="ltx_cite ltx_citemacro_citep">(<a href="#bib.bib1" class="ltx_ref">A, 2020</a>)</cite>.</p></div>
<section id="S1" class="ltx_section"><h2 class="ltx_title ltx_title_section"><span class="ltx_tag ltx_tag_section">1 </span>Introduction</h2>
<p>Transformers <cite class="ltx_cite ltx_citemacro_citet"><a href="#bib.bib2" class="ltx_ref">B</a></cite> use
<math alttext="x^{2}" class="ltx_Math"><mi>x</mi></math> and many others
<cite class="ltx_cite ltx_citemacro_citep">(<a href="#bib.bib1">A</a>; <a href="#bib.bib2">B</a>; <a href="#bib.bib3">C</a>; <a href="#bib.bib4">D</a>)</cite>.
Unknown <cite class="ltx_cite ltx_citemacro_cite"><span class="ltx_ref ltx_missing_citation">foo</span></cite>.</p>
<section id="S1.SS1" class="ltx_subsection"><h3 class="ltx_title"><span class="ltx_tag">1.1 </span>Related work</h3>
<p>See <cite class="ltx_cite"><a href="#bib.bib3">C</a></cite>.</p></section></section>
<section id="bib" class="ltx_bibliography"><h2 class="ltx_title">References</h2><ul class="ltx_biblist">
<li id="bib.bib1" class="ltx_bibitem"><span class="ltx_tag">[1]</span><span class="ltx_bibblock">Ann A.</span>
<span class="ltx_bibblock">Attention &amp; memory.</span><span class="ltx_bibblock">arXiv preprint arXiv:2101.00001, 2021.</span></li>
<li id="bib.bib2" class="ltx_bibitem"><span class="ltx_bibblock">B. Bee, “Graph nets for all,” in Proc. X, 2019.</span></li>
<li id="bib.bib3" class="ltx_bibitem"><span class="ltx_bibblock">C.</span><span class="ltx_bibblock">Third paper.</span></li>
<li id="bib.bib4" class="ltx_bibitem"><span class="ltx_bibblock">D.</span><span class="ltx_bibblock">Fourth paper.</span></li>
</ul></section>
<section id="A1" class="ltx_appendix"><h2 class="ltx_title"><span class="ltx_tag">Appendix A </span>Proofs</h2>
<p>As in <cite class="ltx_cite"><a href="#bib.bib4">D</a></cite>.</p></section>
</article></div></body></html>"""


class ArxivHtmlTest(unittest.TestCase):
    def setUp(self):
        self.p = parse_html(PAGE)

    def test_detects_latexml(self):
        self.assertTrue(is_latexml(PAGE))
        self.assertFalse(is_latexml("<html><body>No HTML for this paper</body></html>"))

    def test_references(self):
        refs = {r["key"]: r for r in self.p["refs"]}
        self.assertEqual(list(refs), ["bib.bib1", "bib.bib2", "bib.bib3", "bib.bib4"])
        self.assertEqual(refs["bib.bib1"]["title"], "Attention & memory")
        self.assertEqual(refs["bib.bib1"]["arxiv_id"], "2101.00001")
        self.assertEqual(refs["bib.bib2"]["title"], "Graph nets for all")   # kiểu IEEE, một bibblock
        self.assertEqual(refs["bib.bib3"]["title"], "Third paper")

    def test_sections_and_appendix_after_bibliography(self):
        self.assertEqual(self.p["sections"], ["Introduction", "Related work", "Proofs"])
        last = self.p["cites"][-1]
        self.assertEqual((last["keys"], last["appendix"]), (["bib.bib4"], True))   # phụ lục nằm sau bibliography

    def test_cites(self):
        cites = self.p["cites"]
        self.assertEqual([c["keys"] for c in cites],
                         [["bib.bib1"], ["bib.bib2"], ["bib.bib1", "bib.bib2", "bib.bib3", "bib.bib4"],
                          ["bib.bib3"], ["bib.bib4"]])                  # bỏ trích dẫn không phân giải được
        self.assertEqual((cites[0]["sec"], cites[1]["sec"], cites[3]["sub"]), (-1, 0, 1))
        self.assertIn("[@]", cites[1]["ctx"])
        self.assertIn("[CITE]", cites[1]["ctx"])
        self.assertIn("x^{2}", cites[1]["ctx"])                        # công thức thay bằng alttext
        self.assertNotIn("ltx_", cites[1]["ctx"])

    def test_features_work_on_html_output(self):
        f = citation_features(self.p)
        self.assertEqual(f["bib.bib3"]["n_mentions"], 2)
        self.assertTrue(f["bib.bib3"]["in_related"])
        self.assertTrue(f["bib.bib4"]["only_in_list"] is False)        # có lần trích riêng trong phụ lục
        self.assertFalse(f["bib.bib4"]["appendix_only"])


if __name__ == "__main__":
    unittest.main()
