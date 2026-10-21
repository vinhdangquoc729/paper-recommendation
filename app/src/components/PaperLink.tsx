import { ReactNode, useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "../prefs";
import type { PaperSummary } from "../types";
import { PaperMeta } from "./PaperMeta";
import { Tex } from "./Tex";

const OPEN_DELAY_MS = 350;    // tránh bật khung khi chỉ lướt chuột qua
const CLOSE_DELAY_MS = 150;   // đủ thời gian để di chuột từ tên bài xuống khung

/** Link tới trang đọc bài; rê chuột (hoặc focus bằng bàn phím) thì hiện khung xem nhanh. */
export function PaperLink({ paper, className, children }: {
  paper: PaperSummary; className?: string; children?: ReactNode;
}) {
  const { t, authors } = useI18n();
  const [open, setOpen] = useState(false);
  const [alignRight, setAlignRight] = useState(false);
  const timer = useRef<number>();
  const anchor = useRef<HTMLSpanElement>(null);
  const tipId = useId();

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const schedule = (next: boolean) => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      if (next && anchor.current) {
        // khung rộng 460px: nếu tên bài nằm sát mép phải thì canh khung theo mép phải
        setAlignRight(anchor.current.getBoundingClientRect().left + 470 > window.innerWidth);
      }
      setOpen(next);
    }, next ? OPEN_DELAY_MS : CLOSE_DELAY_MS);
  };

  return (
    <span
      ref={anchor}
      className="peek-anchor"
      onMouseEnter={() => schedule(true)}
      onMouseLeave={() => schedule(false)}
      onFocus={() => schedule(true)}
      onBlur={() => schedule(false)}
      onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
    >
      <Link className={className} to={`/paper/${paper.id}`} aria-describedby={open ? tipId : undefined}
            onClick={() => setOpen(false)}>
        {children ?? <Tex text={paper.title} />}
      </Link>
      {open && (
        <span id={tipId} role="tooltip" className={`peek ${alignRight ? "right" : ""}`}>
          <span className="peek-title"><Tex text={paper.title} /></span>
          <span className="peek-authors">{authors(paper.authors, 8)}</span>
          <PaperMeta paper={paper} />
          {paper.abstract_snippet ? (
            <span className="peek-abstract"><Tex text={paper.abstract_snippet} /></span>
          ) : (
            <span className="peek-abstract muted">{t("peek.noAbstract")}</span>
          )}
          <span className="peek-hint">{t("peek.hint")}</span>
        </span>
      )}
    </span>
  );
}
