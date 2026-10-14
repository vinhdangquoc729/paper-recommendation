import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { PaperRow } from "../components/PaperRow";
import type { MessageKey } from "../i18n";
import { useI18n } from "../prefs";
import type { Meta, PaperFilters } from "../types";
import { useAsync } from "../useAsync";

const PAGE_SIZE = 20;

// label: khoá i18n, hoặc thuật ngữ hội nghị giữ nguyên ở mọi ngôn ngữ
const DECISION_OPTIONS: { value: string; label: MessageKey | string; i18n: boolean }[] = [
  { value: "", label: "papers.all", i18n: true },
  { value: "accepted", label: "papers.accepted", i18n: true },
  { value: "accept_oral", label: "Oral", i18n: false },
  { value: "accept_spotlight", label: "Spotlight", i18n: false },
  { value: "accept_poster", label: "Poster", i18n: false },
  { value: "reject", label: "Reject", i18n: false },
];

/** Màn chính: ô tìm kiếm trống thì hiện gợi ý theo hồ sơ, có từ khoá thì hiện kết quả tìm kiếm. */
export function PapersPage({ meta }: { meta: Meta | null }) {
  const { t, int } = useI18n();
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
          placeholder={t("papers.placeholder")}
          aria-label={t("papers.searchAria")}
        />
        <button type="submit" className="primary">{t("papers.search")}</button>
        {isSearch && (
          <button type="button" onClick={() => update({ q: null })}>{t("papers.backToRecs")}</button>
        )}
      </form>

      <div className="columns">
        <aside className="sidebar">
          <fieldset>
            <legend>{t("papers.filters")}</legend>
            <label>
              {t("papers.venue")}
              <select value={filters.venue ?? ""} onChange={(e) => update({ venue: e.target.value || null })}>
                <option value="">{t("papers.all")}</option>
                {meta?.venues.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
              </select>
            </label>
            <label>
              {t("papers.year")}
              <select value={filters.year ?? ""} onChange={(e) => update({ year: e.target.value || null })}>
                <option value="">{t("papers.all")}</option>
                {meta?.years.slice().reverse().map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <label>
              {t("papers.decision")}
              <select value={filters.decision ?? ""} onChange={(e) => update({ decision: e.target.value || null })}>
                {DECISION_OPTIONS.map((d) => (
                  <option key={d.value} value={d.value}>{d.i18n ? t(d.label as MessageKey) : d.label}</option>
                ))}
              </select>
            </label>
            <label>
              <input
                type="checkbox"
                checked={!!filters.has_code}
                onChange={(e) => update({ code: e.target.checked ? "1" : null })}
              />{" "}
              {t("papers.onlyCode")}
            </label>
          </fieldset>
          {!isSearch && (
            <p className="small muted">
              {t("papers.hintBefore")} <Link to="/account">{t("nav.account")}</Link>{t("papers.hintAfter")}
            </p>
          )}
        </aside>

        <section>
          <div className="list-head">
            <h1>{isSearch ? t("papers.titleSearch", { q }) : t("papers.titleRecs")}</h1>
            {data && <span className="muted">{t("papers.count", { n: int(data.total) })}</span>}
          </div>

          {error && <p className="error">{error}</p>}
          {loading && !data && <p className="muted">{t("common.loading")}</p>}
          {data && data.items.length === 0 && (
            <p className="muted">{t("papers.empty")}</p>
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
              <button disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>{t("papers.prev")}</button>
              <span>{t("papers.pageOf", { p: page, n: totalPages })}</span>
              <button disabled={page >= totalPages} onClick={() => update({ page: String(page + 1) })}>{t("papers.next")}</button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
