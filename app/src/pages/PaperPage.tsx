import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { FeedbackBar } from "../components/FeedbackBar";
import { PaperLink } from "../components/PaperLink";
import { PaperMeta } from "../components/PaperMeta";
import { PdfViewer } from "../components/PdfViewer";
import { authorsShort, dateVi, decimal, decisionLabel, signed } from "../format";
import { useAsync } from "../useAsync";

/** Đọc một bài: PDF bên trái (70%), thông tin bên phải (30%); bên dưới là "Có thể bạn quan tâm". */
export function PaperPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const paper = useAsync(() => api.paper(id), [id]);
  const related = useAsync(() => api.related(id, 10), [id]);
  const p = paper.data;

  return (
    <>
      <p className="small">
        <a href="#" onClick={(e) => { e.preventDefault(); navigate(-1); }}>Quay lại</a>
      </p>

      {paper.error && <p className="error">{paper.error}</p>}
      {paper.loading && !p && <p className="muted">Đang tải...</p>}

      {p && (
        <article key={p.id} className="reader">
          <section className="reader-pdf" aria-label="Bản PDF">
            <PdfViewer paperId={p.id} cached={p.pdf_cached} openreviewPdf={p.pdf_url} />
          </section>

          <aside className="reader-info">
            <h1>{p.title}</h1>
            <div className="paper-authors">{authorsShort(p.authors, 20)}</div>
            <PaperMeta paper={p} showArea={false} />
            <div className="links">
              <a href={p.openreview_url} target="_blank" rel="noreferrer">Trang OpenReview</a>
              {p.pdf_cached && <a href={api.pdfUrl(p.id)} target="_blank" rel="noreferrer">PDF tab mới</a>}
              {p.code_url && <a href={p.code_url} target="_blank" rel="noreferrer">Mã nguồn</a>}
            </div>
            <FeedbackBar paper={p} />

            {p.tldr && (
              <>
                <h3>TL;DR</h3>
                <div className="tldr-box">{p.tldr}</div>
              </>
            )}

            <h3>Tóm tắt</h3>
            <div className="abstract">{p.abstract || <span className="muted">Không có tóm tắt.</span>}</div>

            <h3>Thông tin</h3>
            <table className="info">
              <tbody>
                <tr><th>Hội nghị</th><td>{p.venue} {p.year}</td></tr>
                <tr><th>Kết quả</th><td>{decisionLabel(p.decision)}</td></tr>
                {p.primary_area && <tr><th>Lĩnh vực</th><td>{p.primary_area}</td></tr>}
                {p.keywords.length > 0 && <tr><th>Từ khoá</th><td>{p.keywords.join(", ")}</td></tr>}
                {p.first_seen && <tr><th>Công khai từ</th><td>{dateVi(p.first_seen)}</td></tr>}
                <tr>
                  <th>Đánh giá</th>
                  <td>
                    {p.reviews.n_reviews > 0 ? (
                      <>
                        {p.reviews.n_reviews} review, điểm {p.reviews.ratings.map((r) => decimal(r, 0)).join(", ")}
                        {p.reviews.rating_z !== null && (
                          <div className="muted">So với cùng hội nghị: {signed(p.reviews.rating_z)}</div>
                        )}
                      </>
                    ) : (
                      <span className="muted">Không có review công khai</span>
                    )}
                  </td>
                </tr>
                {p.quality !== null && (
                  <tr>
                    <th>Chất lượng</th>
                    <td>{decimal(p.quality)} <span className="muted">(0 đến 1)</span></td>
                  </tr>
                )}
                {p.versions.length > 1 && (
                  <tr>
                    <th>Các lần nộp</th>
                    <td>
                      {p.versions.map((v) => (
                        <div key={v.forum_id}>
                          <a href={v.url} target="_blank" rel="noreferrer">{v.venue} {v.year}</a>: {decisionLabel(v.decision)}
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

      <h2>Có thể bạn quan tâm</h2>
      {related.error && <p className="error">{related.error}</p>}
      {related.loading && !related.data && <p className="muted">Đang tải...</p>}
      {related.data && related.data.length === 0 && <p className="muted">Chưa tìm được bài liên quan.</p>}
      {related.data && related.data.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Bài báo</th>
              <th>Hội nghị</th>
              <th>Kết quả</th>
              <th className="num" title="Độ tương đồng nội dung (cosine)">Tương đồng</th>
            </tr>
          </thead>
          <tbody>
            {related.data.map((r, i) => (
              <tr key={r.id}>
                <td className="num">{i + 1}</td>
                <td>
                  <PaperLink paper={r} />
                  <div className="small muted">{authorsShort(r.authors, 4)}</div>
                </td>
                <td style={{ whiteSpace: "nowrap" }}>{r.venue} {r.year}</td>
                <td>{decisionLabel(r.decision)}</td>
                <td className="num">{r.score !== null ? decimal(r.score) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
