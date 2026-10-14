import unittest

from crawler.latex import extract_citations, flatten_tex

MAIN = r"""
\documentclass{article}
\newcommand{\mycite}{\cite{shouldnotcount}}
\begin{document}
\begin{abstract} We build on transformers~\cite{vaswani2017}. \end{abstract}
\section{Introduction}
Graph networks \citep{gin, gcn, gat, sage} are popular. % \cite{commented}
\input{sections/method}
\appendix
\section{Proofs}
As in \citet[Thm.~2]{xu2019}, the result follows.
\end{document}
"""
METHOD = r"""
\section{Method}
\subsection{Model}
We use the encoder of \citet{vaswani2017} and the readout of \cite{xu2019}.
"""


class TestLatex(unittest.TestCase):
    def setUp(self):
        tex = flatten_tex({"paper/main.tex": MAIN, "paper/sections/method.tex": METHOD})
        self.out = extract_citations(tex)
        self.cites = self.out["cites"]

    def test_input_is_inlined_and_preamble_and_comments_skipped(self):
        keys = [k for c in self.cites for k in c["keys"]]
        self.assertIn("xu2019", keys)
        self.assertNotIn("shouldnotcount", keys)
        self.assertNotIn("commented", keys)

    def test_sections_and_list_citations(self):
        names = self.out["sections"]
        first = self.cites[0]
        self.assertEqual(first["keys"], ["vaswani2017"])
        self.assertEqual(first["sec"], -1)                       # trong abstract, trước section đầu tiên
        lst = self.cites[1]
        self.assertEqual(lst["keys"], ["gin", "gcn", "gat", "sage"])
        self.assertEqual(names[lst["sec"]], "Introduction")
        method = self.cites[2]
        self.assertEqual(names[method["sec"]], "Method")
        self.assertEqual(names[method["sub"]], "Model")
        self.assertFalse(method["appendix"])

    def test_appendix_and_optional_argument(self):
        last = self.cites[-1]
        self.assertEqual(last["keys"], ["xu2019"])
        self.assertTrue(last["appendix"])
        self.assertIn("[@]", last["ctx"])

    def test_context_marks_other_citations(self):
        method = self.cites[2]
        self.assertIn("[@]", method["ctx"])
        self.assertIn("[CITE]", method["ctx"])


if __name__ == "__main__":
    unittest.main()
