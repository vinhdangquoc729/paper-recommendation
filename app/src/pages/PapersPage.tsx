import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { PaperRow } from "../components/PaperRow";
import type { Meta, PaperFilters } from "../types";
import { useAsync } from "../useAsync";

const PAGE_SIZE = 20;

const DECISION_OPTIONS = [
  { value: "", label: "Tất cả" },
  { value: "accepted", label: "Đã được nhận" },
  { value: "accept_oral", label: "Oral" },
  { value: "accept_spotlight", label: "Spotlight" },
  { value: "accept_poster", label: "Poster" },
  { value: "reject", label: "Reject" },
];

/** Màn chính: ô tìm kiếm trống thì hiện gợi ý theo hồ sơ, có từ khoá thì hiện kết quả tìm kiếm. */
export function PapersPage({ meta }: { meta: Meta | null }) {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? 1));
  const filters: PaperFilters = {
    venue: params.get("venue") || undefined,
    year: params.get("year") ? Number(params.get("year")) : undefined,
    decision: params.get("decision") || undefined,
    has_code: params.get("code") === "1" || undefined,
  };

  const [draft, setDraft] = useState(q);
  useEffect(() => setDraft(q), [q]);

  const { data, error, loading } = useAsync(
    () => api.papers(q, filters, (page - 1) * PAGE_SIZE, PAGE_SIZE),
    [params.toString()],
  );

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page");
    setParams(next);
  };

  const onSearch = (e: FormEvent) => {
    e.preventDefault();
    update({ q: draft.trim() || null });
  };

  const isSearch = q.trim() !== "";
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <>
      <form className="searchbar" onSubmit={onSearch} role="search">
        <input
          type="search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Nhập chủ đề, phương pháp hoặc tên bài. Để trống để xem gợi ý dành cho bạn."
          aria-label="Từ khoá tìm kiếm"
        />
        <button type="submit" className="primary">Tìm kiếm</button>
        {isSearch && (
          <button type="button" onClick={() => update({ q: null })}>Về gợi ý</button>
        )}
      </form>

      <div className="columns">
        <aside className="sidebar">
          <fieldset>
            <legend>Bộ lọc</legend>
            <label>
              Hội nghị
              <select value={filters.venue ?? ""} onChange={(e) => update({ venue: e.target.value || null })}>
                <option value="">Tất cả</option>
                {meta?.venues.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
              </select>
            </label>
            <label>
              Năm
              <select value={filters.year ?? ""} onChange={(e) => update({ year: e.target.value || null })}>
                <option value="">Tất cả</option>
                {meta?.years.slice().reverse().map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <label>
              Kết quả
              <select value={filters.decision ?? ""} onChange={(e) => update({ decision: e.target.value || null })}>
                {DECISION_OPTIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={!!filters.has_code}
                onChange={(e) => update({ code: e.target.checked ? "1" : null })}
              />{" "}
              Chỉ bài có mã nguồn
            </label>
          </fieldset>
          {!isSearch && (
            <p className="small muted">
              Gợi ý dựa trên hồ sơ và sở thích trong trang <Link to="/account">Tài khoản</Link>.
            </p>
          )}
        </aside>

        <section>
          <div className="list-head">
            <h1>{isSearch ? `Kết quả cho "${q}"` : "Gợi ý cho bạn"}</h1>
            {data && <span className="muted">{data.total.toLocaleString("vi-VN")} bài</span>}
          </div>

          {error && <p className="error">{error}</p>}
          {loading && !data && <p className="muted">Đang tải...</p>}
          {data && data.items.length === 0 && (
            <p className="muted">Không có bài nào khớp. Thử bỏ bớt bộ lọc hoặc đổi từ khoá.</p>
          )}

          {data && (
            <ol className="paper-list" style={{ opacity: loading ? 0.5 : 1 }}>
              {data.items.map((p, i) => (
                <PaperRow key={p.id} paper={p} index={data.offset + i + 1} />
              ))}
            </ol>
          )}

          {data && data.total > PAGE_SIZE && (
            <div className="pager">
              <button disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>Trang trước</button>
              <span>Trang {page} / {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => update({ page: String(page + 1) })}>Trang sau</button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
