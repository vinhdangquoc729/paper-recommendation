import { isAccepted } from "../format";
import { useI18n } from "../prefs";
import type { PaperSummary } from "../types";

/** Dòng thông tin ngắn: hội nghị, kết quả, điểm review, có code. */
export function PaperMeta({ paper, showArea = true }: { paper: PaperSummary; showArea?: boolean }) {
  const { t, decision, signed } = useI18n();
  const strong = paper.decision === "accept_oral" || paper.decision === "accept_spotlight";
  return (
    <div className="meta">
      <span>{paper.venue} {paper.year}</span>
      <span>
        <span className={`tag ${strong ? "good" : isAccepted(paper.decision) ? "" : "weak"}`}>
          {decision(paper.decision)}
        </span>
      </span>
      {paper.n_ratings > 0 && paper.rating_z !== null && (
        <span title={t("meta.reviewTitle")}>
          {t("meta.review", { z: signed(paper.rating_z), n: paper.n_ratings })}
        </span>
      )}
      {paper.has_code && <span>{t("meta.hasCode")}</span>}
      {showArea && paper.primary_area && <span>{paper.primary_area}</span>}
    </div>
  );
}
