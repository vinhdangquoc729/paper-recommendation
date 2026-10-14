import unittest

from crawler.latex import citation_features, extract_citations, flatten_tex, section_kind
from crawler.parse import parse_bib

TEX = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
Many works \citep{a1, a2, a3, a4, core} study this. We follow \citet{core}.
\section{Related Work}
See \cite{a1, a2, a3, a4}.
\section{Our Method}
We extend \citet{core} with the loss of \cite{loss}.
\section{Experiments}
We compare with \cite{core} on \cite{data}.
\appendix
\section{Extra}
More in \cite{appx}.
\end{document}
"""

BIB = r"""
@string{iclr = "ICLR"}
@inproceedings{core,
  title = {{Attention} Is All You Need},
  booktitle = iclr,
  year = 2017
}
@article{loss,
  title = "A Loss with = sign inside",
  journal = {arXiv preprint arXiv:2101.00001}
}
@misc{unused, title={Never cited}}
"""


class TestCitationFeatures(unittest.TestCase):
    def setUp(self):
        self.f = citation_features(extract_citations(flatten_tex({"main.tex": TEX})))

    def test_core_reference(self):
        core = self.f["core"]
        self.assertEqual(core["n_mentions"], 4)
        self.assertEqual(core["n_sections"], 3)
        self.assertTrue(core["in_intro"] and core["in_method"] and core["in_experiment"])
        self.assertFalse(core["only_in_list"])

    def test_list_only_reference(self):
        a1 = self.f["a1"]
        self.assertTrue(a1["only_in_list"])
        self.assertTrue(a1["in_related"])
        self.assertFalse(a1["in_method"])
        self.assertEqual(a1["min_list_size"], 4)

    def test_appendix_only(self):
        self.assertTrue(self.f["appx"]["appendix_only"])
        self.assertFalse(self.f["core"]["appendix_only"])

    def test_section_kind(self):
        self.assertEqual(section_kind("Related Work and Background"), "related")
        self.assertEqual(section_kind("Experimental Setup"), "experiment")
        self.assertEqual(section_kind("Conclusion"), "other")


class TestParseBib(unittest.TestCase):
    def test_entries(self):
        items = {i["key"]: i for i in parse_bib(BIB)}
        self.assertEqual(set(items), {"core", "loss", "unused"})          # bỏ @string
        self.assertEqual(items["core"]["title"], "Attention Is All You Need")
        self.assertEqual(items["loss"]["title"], "A Loss with = sign inside")
        self.assertEqual(items["loss"]["arxiv_id"], "2101.00001")


if __name__ == "__main__":
    unittest.main()
