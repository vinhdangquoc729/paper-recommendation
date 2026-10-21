import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../prefs";

type State =
  | { kind: "arxiv" }
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "error"; rateLimitedMin: number | null };

const arxivPdf = (id: string) => `https://arxiv.org/pdf/${id}`;

/** PDF nhúng trong trang. Thứ tự: bản OpenReview đã cache, bản arXiv (nhúng thẳng, không giới hạn lượt), còn lại thì
 *  chỉ tải từ OpenReview khi người dùng bấm (giới hạn khoảng 26 lượt mỗi giờ). */
export function PdfViewer({ paperId, cached, openreviewPdf, arxivId }: {
  paperId: string; cached: boolean; openreviewPdf: string; arxivId: string | null;
}) {
  const { t } = useI18n();
  const initial = (): State => cached ? { kind: "ready" } : arxivId ? { kind: "arxiv" } : { kind: "idle" };
  const [state, setState] = useState<State>(initial);
  useEffect(() => setState(initial()), [paperId, cached, arxivId]);

  const load = async () => {
    setState({ kind: "loading" });
    try {
      await api.preparePdf(paperId);
      setState({ kind: "ready" });
    } catch (e) {
      const limited = e instanceof ApiError && e.status === 429;
      const minutes = limited ? Math.ceil((e.retryAfterS ?? 3600) / 60) : null;
      setState({ kind: "error", rateLimitedMin: minutes });
    }
  };

  if (state.kind === "arxiv" && arxivId) {
    return (
      <>
        <p className="pdf-source small muted">
          {t("pdf.fromArxiv")}{" "}
          <a href={arxivPdf(arxivId)} target="_blank" rel="noreferrer">{t("pdf.newTab")}</a>{" | "}
          <a href="#" onClick={(e) => { e.preventDefault(); setState({ kind: "idle" }); }}>{t("pdf.switchToOR")}</a>
        </p>
        <iframe className="pdf-frame" src={arxivPdf(arxivId)} title={t("pdf.frameTitle")} />
      </>
    );
  }

  if (state.kind === "ready") {
    return (
      <>
        {arxivId && (
          <p className="pdf-source small muted">
            {t("pdf.fromOR")}{" "}
            <a href="#" onClick={(e) => { e.preventDefault(); setState({ kind: "arxiv" }); }}>{t("pdf.switchToArxiv")}</a>
          </p>
        )}
        <iframe className="pdf-frame" src={api.pdfUrl(paperId)} title={t("pdf.frameTitle")} />
      </>
    );
  }

  return (
    <div className="pdf-placeholder">
      <p className="pdf-placeholder-title">{t("pdf.title")}</p>
      {state.kind === "error" ? (
        state.rateLimitedMin !== null
          ? <p>{t("pdf.rateLimited", { m: state.rateLimitedMin })}</p>
          : <p className="error">{t("pdf.unavailable")}</p>
      ) : (
        <p className="muted">{t("pdf.notCached")}</p>
      )}
      <p>
        <button className="primary" onClick={load} disabled={state.kind === "loading"}>
          {state.kind === "loading" ? t("pdf.loading") : t("pdf.load")}
        </button>{" "}
        {t("pdf.or")} <a href={openreviewPdf} target="_blank" rel="noreferrer">{t("pdf.openOnOR")}</a>
        {arxivId && (
          <>
            {" | "}
            <a href="#" onClick={(e) => { e.preventDefault(); setState({ kind: "arxiv" }); }}>{t("pdf.switchToArxiv")}</a>
          </>
        )}
      </p>
    </div>
  );
}
