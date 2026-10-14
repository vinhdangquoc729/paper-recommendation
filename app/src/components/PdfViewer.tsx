import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useI18n } from "../prefs";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "error"; rateLimitedMin: number | null };

/** PDF nhúng trong trang. Chỉ tải khi người dùng bấm (OpenReview giới hạn số lượt tải mỗi giờ). */
export function PdfViewer({ paperId, cached, openreviewPdf }: {
  paperId: string; cached: boolean; openreviewPdf: string;
}) {
  const { t } = useI18n();
  const [state, setState] = useState<State>(cached ? { kind: "ready" } : { kind: "idle" });
  useEffect(() => setState(cached ? { kind: "ready" } : { kind: "idle" }), [paperId, cached]);

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

  if (state.kind === "ready") {
    return <iframe className="pdf-frame" src={api.pdfUrl(paperId)} title={t("pdf.frameTitle")} />;
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
      </p>
    </div>
  );
}
