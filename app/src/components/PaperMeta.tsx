import { decisionLabel, isAccepted, signed } from "../format";
import type { PaperSummary } from "../types";

/** Dòng thông tin ngắn: hội nghị, kết quả, điểm review, có code. */
export function PaperMeta({ paper, showArea = true }: { paper: PaperSummary; showArea?: boolean }) {
  const strong = paper.decision === "accept_oral" || paper.decision === "accept_spotlight";
  return (
    <div className="meta">
      <span>{paper.venue} {paper.year}</span>
      <span>
        <span className={`tag ${strong ? "good" : isAccepted(paper.decision) ? "" : "weak"}`}>
          {decisionLabel(paper.decision)}
        </span>
      </span>
      {paper.n_ratings > 0 && paper.rating_z !== null && (
        <span title="Điểm review trung bình, chuẩn hoá theo hội nghị và năm (0 là mức trung bình)">
          Review {signed(paper.rating_z)} ({paper.n_ratings} đánh giá)
        </span>
      )}
      {paper.has_code && <span>Có mã nguồn</span>}
      {showArea && paper.primary_area && <span>{paper.primary_area}</span>}
    </div>
  );
}
