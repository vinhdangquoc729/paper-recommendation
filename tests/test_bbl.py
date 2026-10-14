import gzip
import io
import tarfile
import unittest

from crawler.arxiv import extract_bbl
from crawler.parse import latex_to_text, norm_title, parse_bbl

NATBIB = r"""
\begin{thebibliography}{78}
\providecommand{\natexlab}[1]{#1}

\bibitem[Abboud et~al.(2021)Abboud, Ceylan, Grohe, and Lukasiewicz]{abboud2020surprising}
Abboud, R., Ceylan, {\.I}.~{\.I}., Grohe, M., and Lukasiewicz, T.
\newblock The surprising power of graph neural networks with random node initialization.
\newblock In \emph{Proceedings of the Thirtieth International Joint Conference on Artifical Intelligence ({IJCAI})}, 2021.

\bibitem[Arvind et~al.(2020)Arvind, Fuhlbr{\"{u}}ck, K{\"{o}}bler, and Verbitsky]{arvind2020onweisfeiler}
Arvind, V., Fuhlbr{\"{u}}ck, F., K{\"{o}}bler, J., and Verbitsky, O.
\newblock On {W}eisfeiler-{L}eman invariance: Subgraph counts and related graph properties.
\newblock \emph{Journal of Computer and System Sciences}, 113:\penalty0 42--59, 2020.

\bibitem[Bar-Shalom et~al.(2024{\natexlab{a}})Bar-Shalom, Bevilacqua, and Maron]{bar2024subgraphormer}
Bar-Shalom, G., Bevilacqua, B., and Maron, H.
\newblock Subgraphormer: Unifying subgraph gnns and graph transformers via graph products.
\newblock \emph{arXiv preprint arXiv:2402.08450}, 2024{\natexlab{a}}.

\end{thebibliography}
"""

BIBLATEX = r"""
\entry{vaswani2017}{inproceedings}{}
  \field{title}{Attention is {All} you Need}
  \field{year}{2017}
\endentry
\entry{gpt4}{misc}{}
  \field{title}{{GPT}-4 Technical Report}
  \field{eprint}{2303.08774}
\endentry
"""


class TestBbl(unittest.TestCase):
    def test_natbib(self):
        items = parse_bbl(NATBIB)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["title"],
                         "The surprising power of graph neural networks with random node initialization")
        self.assertEqual(items[1]["title"],
                         "On Weisfeiler-Leman invariance: Subgraph counts and related graph properties")
        self.assertIsNone(items[0]["arxiv_id"])
        self.assertEqual(items[2]["arxiv_id"], "2402.08450")

    def test_biblatex(self):
        items = parse_bbl(BIBLATEX)
        self.assertEqual(norm_title(items[0]["title"]), norm_title("Attention Is All You Need"))
        self.assertEqual(items[1]["arxiv_id"], "2303.08774")

    def test_latex_to_text(self):
        self.assertEqual(latex_to_text(r"Fuhlbr{\"{u}}ck \& K{\"o}bler"), "Fuhlbruck & Kobler")
        self.assertEqual(latex_to_text(r"\emph{Deep} {L}earning~now"), "Deep Learning now")

    def test_extract_from_tar(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in [("main.tex", b"\\cite{x}"), ("main.bbl", NATBIB.encode()), ("refs.bib", b"@a{x}")]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        status, bbl, has_bib = extract_bbl(buf.getvalue())
        self.assertEqual(status, "ok")
        self.assertTrue(has_bib)
        self.assertEqual(len(parse_bbl(bbl)), 3)

    def test_extract_single_gzip_tex(self):
        status, bbl, _ = extract_bbl(gzip.compress(("\\documentclass{x}" + NATBIB).encode()))
        self.assertEqual(status, "ok")
        self.assertTrue(bbl.startswith("\\begin{thebibliography}"))

    def test_extract_pdf_only(self):
        self.assertEqual(extract_bbl(b"%PDF-1.5 ...")[0], "pdf_only")


if __name__ == "__main__":
    unittest.main()
