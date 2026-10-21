import { useI18n } from "../prefs";
import type { PaperSummary } from "../types";
import { FeedbackBar } from "./FeedbackBar";
import { PaperLink } from "./PaperLink";
import { PaperMeta } from "./PaperMeta";
import { Reasons } from "./Reasons";
import { Tex } from "./Tex";

export function PaperRow({ paper, index }: { paper: PaperSummary; index: number }) {
  const { authors } = useI18n();
  return (
    <li className="paper-row">
      <div className="num">{index}.</div>
      <div>
        <PaperLink className="paper-title" paper={paper} />
        <div className="paper-authors">{authors(paper.authors)}</div>
        <PaperMeta paper={paper} />
        {paper.tldr && <div className="paper-tldr"><Tex text={paper.tldr} /></div>}
        <Reasons reasons={paper.reasons} />
        <FeedbackBar paper={paper} />
      </div>
    </li>
  );
}
