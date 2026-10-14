import { useEffect, useState } from "react";
import { api, ApiError } from "../api";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "error"; message: string; rateLimited: boolean };

/** PDF nhúng trong trang. Chỉ tải khi người dùng bấm (OpenReview giới hạn số lượt tải mỗi giờ). */
export function PdfViewer({ paperId, cached, openreviewPdf }: {
  paperId: string; cached: boolean; openreviewPdf: string;
}) {
  const [state, setState] = useState<State>(cached ? { kind: "ready" } : { kind: "idle" });
  useEffect(() => setState(cached ? { kind: "ready" } : { kind: "idle" }), [paperId, cached]);

  const load = async () => {
    setState({ kind: "loading" });
    try {
      await api.preparePdf(paperId);
      setState({ kind: "ready" });
    } catch (e) {
      const err = e as Error;
      setState({ kind: "error", message: err.message, rateLimited: err instanceof ApiError && err.status === 429 });
    }
  };

  if (state.kind === "ready") {
    return (
      <iframe className="pdf-frame" src={api.pdfUrl(paperId)} title="Bản PDF của bài báo" />
    );
  }

  return (
    <div className="pdf-placeholder">
      <p style={{ fontFamily: "var(--font-text)", fontSize: 18, color: "var(--text)" }}>Bản PDF</p>
      {state.kind === "error" ? (
        <p className={state.rateLimited ? "" : "error"}>{state.message}</p>
      ) : (
        <p className="muted">
          PDF chưa được tải về máy chủ. OpenReview chỉ cho tải khoảng 26 bài mỗi giờ, nên PDF được tải khi bạn cần.
        </p>
      )}
      <p>
        <button className="primary" onClick={load} disabled={state.kind === "loading"}>
          {state.kind === "loading" ? "Đang tải PDF..." : "Xem PDF tại đây"}
        </button>{" "}
        hoặc <a href={openreviewPdf} target="_blank" rel="noreferrer">mở trên OpenReview</a>
      </p>
    </div>
  );
}
