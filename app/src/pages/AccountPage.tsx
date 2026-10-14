import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { PaperLink } from "../components/PaperLink";
import { useI18n } from "../prefs";
import type { AuthoredPaper, Meta, Preferences, Profile } from "../types";
import { useAsync } from "../useAsync";

/** Tài khoản: thông tin cá nhân, OpenReview ID để nhận diện bài đã đăng, và sở thích. */
export function AccountPage({ meta }: { meta: Meta | null }) {
  const { t, time, decision } = useI18n();
  const me = useAsync(() => api.me(), []);
  const [form, setForm] = useState<Profile | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [authoredKey, setAuthoredKey] = useState(0);   // tăng lên để tải lại danh sách bài của tôi

  useEffect(() => {
    if (me.data) setForm(me.data);
  }, [me.data]);

  const authored = useAsync(() => api.authored(), [authoredKey]);
  const saved = useAsync(() => api.saved(), []);

  if (me.error) return <p className="error">{me.error}</p>;
  if (!form) return <p className="muted">{t("common.loading")}</p>;

  const setPref = <K extends keyof Preferences>(key: K, value: Preferences[K]) =>
    setForm({ ...form, preferences: { ...form.preferences, [key]: value } });

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const idChanged = form.openreview_id.trim() !== (me.data?.openreview_id ?? "");
      const res = await api.saveMe(form);
      me.setData(res);
      setSavedAt(time(new Date()));
      if (idChanged) setAuthoredKey((k) => k + 1);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <h1>{t("account.title")}</h1>
      <p className="muted">
        {t("account.introBefore")} <Link to="/">{t("nav.papers")}</Link>{t("account.introAfter")}
      </p>

      <fieldset>
        <legend>{t("account.personal")}</legend>
        <div className="form-grid">
          <label htmlFor="name">{t("account.name")}</label>
          <input id="name" type="text" value={form.display_name}
                 onChange={(e) => setForm({ ...form, display_name: e.target.value })} />

          <label htmlFor="email">{t("account.email")}</label>
          <input id="email" type="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <div className="hint">{t("account.emailHint")}</div>

          <label htmlFor="orid">{t("account.orid")}</label>
          <input id="orid" type="text" value={form.openreview_id} placeholder="~Nguyen_Van_A1"
                 onChange={(e) => setForm({ ...form, openreview_id: e.target.value })} />
          <div className="hint">{t("account.oridHint")}</div>
        </div>
      </fieldset>

      <fieldset>
        <legend>{t("account.myPapers")}</legend>
        <AuthoredTable openreviewId={me.data?.openreview_id ?? ""} rows={authored.data} loading={authored.loading}
                       error={authored.error} />
      </fieldset>

      <PreferencesForm prefs={form.preferences} meta={meta} setPref={setPref} />

      <div className="savebar">
        <button className="primary" onClick={save} disabled={saving}>{saving ? t("account.saving") : t("account.save")}</button>
        {savedAt && !saveError && <span className="muted small">{t("account.savedAt", { time: savedAt })}</span>}
        {saveError && <span className="small" style={{ color: "var(--danger)" }}>{saveError}</span>}
      </div>

      <h2>{t("account.saved")}</h2>
      {saved.data && saved.data.length === 0 && (
        <p className="muted">{t("account.savedEmpty")}</p>
      )}
      {saved.data && saved.data.length > 0 && (
        <table className="grid">
          <thead><tr><th>{t("paper.colPaper")}</th><th>{t("paper.venue")}</th><th>{t("paper.decision")}</th></tr></thead>
          <tbody>
            {saved.data.map((p) => (
              <tr key={p.id}>
                <td><PaperLink paper={p} /></td>
                <td style={{ whiteSpace: "nowrap" }}>{p.venue} {p.year}</td>
                <td>{decision(p.decision)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function AuthoredTable({ openreviewId, rows, loading, error }: {
  openreviewId: string; rows: AuthoredPaper[] | null; loading: boolean; error: string | null;
}) {
  const { t, authors, decision } = useI18n();
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  useEffect(() => {
    setConfirmed(Object.fromEntries((rows ?? []).map((r) => [r.paper.id, r.confirmed])));
  }, [rows]);

  if (!openreviewId) return <p className="muted small">{t("account.needId")}</p>;
  if (error) return <p className="error">{error}</p>;
  if (loading || !rows) return <p className="muted">{t("account.searching")}</p>;
  if (rows.length === 0) {
    return <p className="muted small">{t("account.noneFound", { id: openreviewId })}</p>;
  }

  const toggle = async (id: string, value: boolean) => {
    setConfirmed((c) => ({ ...c, [id]: value }));
    try {
      await api.confirmAuthored(id, value);
    } catch {
      setConfirmed((c) => ({ ...c, [id]: !value }));
    }
  };

  return (
    <>
      <p className="small muted" style={{ marginTop: 0 }}>
        {t("account.found", { n: rows.length })}
      </p>
      <table className="grid">
        <thead>
          <tr>
            <th className="center">{t("account.mine")}</th><th>{t("paper.colPaper")}</th>
            <th>{t("paper.venue")}</th><th>{t("paper.decision")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ paper }) => (
            <tr key={paper.id}>
              <td className="center">
                <input type="checkbox" checked={confirmed[paper.id] ?? true}
                       onChange={(e) => toggle(paper.id, e.target.checked)}
                       aria-label={t("account.mineAria", { title: paper.title })} />
              </td>
              <td>
                <PaperLink paper={paper} />
                <div className="small muted">{authors(paper.authors, 5)}</div>
              </td>
              <td style={{ whiteSpace: "nowrap" }}>{paper.venue} {paper.year}</td>
              <td>{decision(paper.decision)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function PreferencesForm({ prefs, meta, setPref }: {
  prefs: Preferences; meta: Meta | null;
  setPref: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
}) {
  const { t, int } = useI18n();
  const [areaFilter, setAreaFilter] = useState("");
  const areas = useMemo(() => {
    const f = areaFilter.trim().toLowerCase();
    return (meta?.areas ?? []).filter((a) => !f || a.label.toLowerCase().includes(f) || prefs.areas.includes(a.value));
  }, [meta, areaFilter, prefs.areas]);

  const toggleIn = (list: string[], value: string, on: boolean) =>
    on ? [...list, value] : list.filter((x) => x !== value);

  return (
    <fieldset>
      <legend>{t("account.prefs")}</legend>
      <div className="form-grid">
        <label>{t("account.areas")}</label>
        <div>
          <input type="search" placeholder={t("account.areaFilter")} value={areaFilter}
                 onChange={(e) => setAreaFilter(e.target.value)} style={{ width: "100%", marginBottom: 4 }} />
          <div className="checklist">
            {areas.map((a) => (
              <label key={a.value}>
                <input type="checkbox" checked={prefs.areas.includes(a.value)}
                       onChange={(e) => setPref("areas", toggleIn(prefs.areas, a.value, e.target.checked))} />{" "}
                {a.label} <span className="count">({int(a.count)})</span>
              </label>
            ))}
          </div>
          <div className="small muted">{t("account.areasChosen", { n: prefs.areas.length })}</div>
        </div>

        <label>{t("account.venues")}</label>
        <div>
          {meta?.venues.map((v) => (
            <label key={v.value} style={{ marginRight: 16 }}>
              <input type="checkbox" checked={prefs.venues.includes(v.value)}
                     onChange={(e) => setPref("venues", toggleIn(prefs.venues, v.value, e.target.checked))} />{" "}
              {v.label}
            </label>
          ))}
        </div>
        <div className="hint">{t("account.venuesHint")}</div>

        <label htmlFor="kw">{t("account.keywords")}</label>
        <input id="kw" type="text" value={prefs.keywords.join(", ")} placeholder={t("account.keywordsPh")}
               onChange={(e) => setPref("keywords", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
        <div className="hint">{t("account.keywordsHint")}</div>

        <label htmlFor="year">{t("account.yearFrom")}</label>
        <select id="year" value={prefs.year_from ?? ""}
                onChange={(e) => setPref("year_from", e.target.value ? Number(e.target.value) : null)}
                style={{ width: 140 }}>
          <option value="">{t("account.noLimit")}</option>
          {meta?.years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>

        <label>{t("account.options")}</label>
        <div>
          <label style={{ display: "block" }}>
            <input type="checkbox" checked={prefs.include_rejected}
                   onChange={(e) => setPref("include_rejected", e.target.checked)} />{" "}
            {t("account.includeRejected")}
          </label>
          <label style={{ display: "block" }}>
            <input type="checkbox" checked={prefs.only_with_code}
                   onChange={(e) => setPref("only_with_code", e.target.checked)} />{" "}
            {t("account.onlyCode")}
          </label>
        </div>

        <label>{t("account.freshness")}</label>
        <div className="slider">
          <span>{t("account.classic")}</span>
          <input type="range" min={0} max={1} step={0.1} value={prefs.freshness}
                 onChange={(e) => setPref("freshness", Number(e.target.value))} aria-label={t("account.freshness")} />
          <span>{t("account.newest")}</span>
        </div>

        <label>{t("account.diversity")}</label>
        <div className="slider">
          <span>{t("account.focused")}</span>
          <input type="range" min={0} max={1} step={0.1} value={prefs.diversity}
                 onChange={(e) => setPref("diversity", Number(e.target.value))} aria-label={t("account.diversity")} />
          <span>{t("account.diverse")}</span>
        </div>
      </div>
    </fieldset>
  );
}
