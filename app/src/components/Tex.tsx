import katex from "katex";
import { useMemo } from "react";

// $$...$$ hoặc $...$ (bỏ qua \$); phần không khớp, kể cả $ lẻ của abstract bị cắt ngắn, giữ nguyên là chữ
const MATH = /\$\$([\s\S]+?)\$\$|\$((?:\\.|[^$\\])+?)\$/g;
const cache = new Map<string, string>();

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function render(src: string): string {
  let html = cache.get(src);
  if (html === undefined) {
    try {
      // dữ liệu đôi khi bị escape hai lần: "4.7\\%" (xuống dòng + chú thích) -> "4.7\%"
      html = katex.renderToString(src.replace(/\\\\([%&#_$])/g, "\\$1"),
                                  { throwOnError: true, strict: "ignore", output: "html" });
    } catch {
      // khoảng 1% công thức trong kho lỗi (macro riêng của tác giả, LaTeX hỏng): hiện nguyên văn như trước
      html = escapeHtml(`$${src}$`);
    }
    if (cache.size > 2000) cache.clear();
    cache.set(src, html);
  }
  return html;
}

type Part = { math: false; text: string } | { math: true; src: string };

function split(text: string): Part[] {
  const parts: Part[] = [];
  let last = 0;
  for (const m of text.matchAll(MATH)) {
    if (m.index! > last) parts.push({ math: false, text: text.slice(last, m.index).replace(/\\\$/g, "$") });
    parts.push({ math: true, src: (m[1] ?? m[2]).trim() });
    last = m.index! + m[0].length;
  }
  if (last < text.length) parts.push({ math: false, text: text.slice(last).replace(/\\\$/g, "$") });
  return parts;
}

/** Chữ có công thức LaTeX inline (tiêu đề, abstract, TL;DR lấy từ OpenReview): công thức render bằng KaTeX. */
export function Tex({ text }: { text: string }) {
  const parts = useMemo(() => split(text), [text]);
  if (parts.length === 1 && !parts[0].math) return <>{parts[0].text}</>;
  return (
    <>
      {parts.map((p, i) =>
        p.math ? <span key={i} dangerouslySetInnerHTML={{ __html: render(p.src) }} /> : <span key={i}>{p.text}</span>,
      )}
    </>
  );
}

const SYMBOLS: Record<string, string> = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", varepsilon: "ε", theta: "θ", lambda: "λ", mu: "μ",
  pi: "π", rho: "ρ", sigma: "σ", tau: "τ", phi: "φ", varphi: "φ", psi: "ψ", omega: "ω", Phi: "Φ", Psi: "Ψ",
  Omega: "Ω", Delta: "Δ", Sigma: "Σ", ell: "ℓ", infty: "∞", times: "×", cdot: "·", le: "≤", ge: "≥", leq: "≤", geq: "≥",
};

/** Bản chữ thường của chuỗi có LaTeX, cho chỗ không render được HTML (lý do gợi ý, aria-label, tiêu đề tab). */
export function plainTex(text: string): string {
  return text.replace(MATH, (_, a: string | undefined, b: string | undefined) =>
    (a ?? b ?? "")
      .replace(/\\(?:text\w*|math\w*|operatorname|bm|boldsymbol)\{([^}]*)\}/g, "$1")
      .replace(/\\([A-Za-z]+)/g, (_m, name: string) => SYMBOLS[name] ?? "")
      .replace(/[{}^_]/g, "")
      .trim(),
  ).replace(/\\\$/g, "$");
}
