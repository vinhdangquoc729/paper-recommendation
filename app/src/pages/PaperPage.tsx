import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { FeedbackBar } from "../components/FeedbackBar";
import { PaperLink } from "../components/PaperLink";
import { PaperMeta } from "../components/PaperMeta";
import { PdfViewer } from "../components/PdfViewer";
import { Reasons } from "../components/Reasons";
import { Tex } from "../components/Tex";
import { useI18n } from "../prefs";
import { useSession } from "../session";
import { useAsync } from "../useAsync";

/** Đọc một bài: PDF bên trái (70%), thông tin bên phải (30%); bên dưới là "Có thể bạn quan tâm". */
export function PaperPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { t, authors, date, decimal, decision, signed } = useI18n();
  const paper = useAsync(() => api.paper(id), [id]);
  const related = useAsync(() => api.related(id, 10), [id]);
  const p = paper.data;
  const { session } = useSession();

  // mở bài = một lượt "clicked"; server tính là đã đọc nếu người dùng bật tuỳ chọn đó trong Tài khoản
  useEffect(() => {
    if (session.logged_in && id) api.feedback(id, "clicked").catch(() => {});
  }, [id, session.logged_in]);

  return (
    <>
      <p className="small">
        <a href="#" onClick={(e) => { e.preventDefault(); navigate(-1); }}>{t("common.back")}</a>
      </p>

      {paper.error && <p className="error">{paper.error}</p>}
      {paper.loading && !p && <p className="muted">{t("common.loading")}</p>}

      {p && (
        <article key={p.id} className="reader">
          <section className="reader-pdf" aria-label={t("pdf.title")}>
            <PdfViewer paperId={p.id} cached={p.pdf_cached} openreviewPdf={p.pdf_url} arxivId={p.arxiv_id} />
          </section>

          <aside className="reader-info">
            <h1><Tex text={p.title} /></h1>
            <div className="paper-authors">{authors(p.authors, 20)}</div>
            <PaperMeta paper={p} showArea={false} />
            <div className="links">
              <a href={p.openreview_url} target="_blank" rel="noreferrer">{t("paper.openreview")}</a>
              {p.arxiv_id && <a href={`https://arxiv.org/abs/${p.arxiv_id}`} target="_blank" rel="noreferrer">arXiv</a>}
              {p.pdf_cached && <a href={api.pdfUrl(p.id)} target="_blank" rel="noreferrer">{t("paper.pdfNewTab")}</a>}
              {p.code_url && <a href={p.code_url} target="_blank" rel="noreferrer">{t("paper.code")}</a>}
            </div>
            <FeedbackBar paper={p} />

            {p.tldr && (
              <>
                <h3>TL;DR</h3>
                <div className="tldr-box"><Tex text={p.tldr} /></div>
              </>
            )}

            <h3>{t("paper.abstract")}</h3>
            <div className="abstract">{p.abstract ? <Tex text={p.abstract} /> : <span className="muted">{t("paper.noAbstract")}</span>}</div>

            <h3>{t("paper.info")}</h3>
            <table className="info">
              <tbody>
                <tr><th>{t("paper.venue")}</th><td>{p.venue} {p.year}</td></tr>
                <tr><th>{t("paper.decision")}</th><td>{decision(p.decision)}</td></tr>
                {p.primary_area && <tr><th>{t("paper.area")}</th><td>{p.primary_area}</td></tr>}
                {p.keywords.length > 0 && <tr><th>{t("paper.keywords")}</th><td>{p.keywords.join(", ")}</td></tr>}
                {p.first_seen && <tr><th>{t("paper.firstSeen")}</th><td>{date(p.first_seen)}</td></tr>}
                <tr>
                  <th>{t("paper.reviews")}</th>
                  <td>
                    {p.reviews.n_reviews > 0 ? (
                      <>
                        {t("paper.reviewsLine", { n: p.reviews.n_reviews, scores: p.reviews.ratings.map((r) => decimal(r, 0)).join(", ") })}
                        {p.reviews.rating_z !== null && (
                          <div className="muted">{t("paper.vsVenue", { z: signed(p.reviews.rating_z) })}</div>
                        )}
                      </>
                    ) : (
                      <span className="muted">{t("paper.noReviews")}</span>
                    )}
                  </td>
                </tr>
                {p.quality !== null && (
                  <tr>
                    <th>{t("paper.quality")}</th>
                    <td>{decimal(p.quality)} <span className="muted">{t("paper.qualityScale")}</span></td>
                  </tr>
                )}
                {p.versions.length > 1 && (
                  <tr>
                    <th>{t("paper.versions")}</th>
                    <td>
                      {p.versions.map((v) => (
                        <div key={v.forum_id}>
                          <a href={v.url} target="_blank" rel="noreferrer">{v.venue} {v.year}</a>: {decision(v.decision)}
                        </div>
                      ))}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </aside>
        </article>
      )}

      <h2>{t("paper.related")}</h2>
      {related.error && <p className="error">{related.error}</p>}
      {related.loading && !related.data && <p className="muted">{t("common.loading")}</p>}
      {related.data && related.data.length === 0 && <p className="muted">{t("paper.relatedEmpty")}</p>}
      {related.data && related.data.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>{t("paper.colPaper")}</th>
              <th>{t("paper.venue")}</th>
              <th>{t("paper.decision")}</th>
            </tr>
          </thead>
          <tbody>
            {related.data.map((r, i) => (
              <tr key={r.id}>
                <td className="num">{i + 1}</td>
                <td>
                  <PaperLink paper={r} />
                  <div className="small muted">{authors(r.authors, 4)}</div>
                  <Reasons reasons={r.reasons} />
                </td>
                <td style={{ whiteSpace: "nowrap" }}>{r.venue} {r.year}</td>
                <td>{decision(r.decision)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
