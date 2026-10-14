import { authorsShort } from "../format";
import type { PaperSummary } from "../types";
import { FeedbackBar } from "./FeedbackBar";
import { PaperLink } from "./PaperLink";
import { PaperMeta } from "./PaperMeta";

export function PaperRow({ paper, index }: { paper: PaperSummary; index: number }) {
  return (
    <li className="paper-row">
      <div className="num">{index}.</div>
      <div>
        <PaperLink className="paper-title" paper={paper} />
        <div className="paper-authors">{authorsShort(paper.authors)}</div>
        <PaperMeta paper={paper} />
        {paper.tldr && <div className="paper-tldr">{paper.tldr}</div>}
        {paper.reasons.length > 0 && (
          <div className="paper-reasons">
            <b>Vì sao gợi ý:</b> {paper.reasons.join("; ")}
          </div>
        )}
        <FeedbackBar paper={paper} />
      </div>
    </li>
  );
}
