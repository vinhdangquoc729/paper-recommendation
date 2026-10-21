import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../prefs";
import type { Meta, Preferences, Profile } from "../types";

const SAVE_DELAY_MS = 600;

/** Sở thích tác động lên thứ hạng gợi ý, sửa ngay ở trang danh sách. Lưu vào hồ sơ (cùng dữ liệu với trang Tài khoản),
 *  lưu xong gọi onSaved để danh sách tải lại. */
export function RankingPrefs({ meta, onSaved }: { meta: Meta | null; onSaved: () => void }) {
  const { t } = useI18n();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [rev, setRev] = useState(0);          // tăng mỗi lần sửa; > 0 thì cần lưu
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [kwDraft, setKwDraft] = useState("");

  useEffect(() => {
    api.me().then((p) => {
      setProfile(p);
      setKwDraft(p.preferences.keywords.join(", "));
    }).catch(() => setStatus("error"));
  }, []);

  useEffect(() => {
    if (rev === 0 || !profile) return;
    const timer = setTimeout(async () => {
      setStatus("saving");
      try {
        await api.saveMe(profile);
        setStatus("saved");
        onSaved();
      } catch {
        setStatus("error");
      }
    }, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
    // chỉ lưu khi người dùng sửa (rev đổi), không lưu lúc mới tải
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rev]);

  if (!profile) return null;
  const prefs = profile.preferences;

  const setPref = <K extends keyof Preferences>(key: K, value: Preferences[K]) => {
    setProfile({ ...profile, preferences: { ...prefs, [key]: value } });
    setRev((r) => r + 1);
  };
  const commitKeywords = () => {
    const kws = kwDraft.split(",").map((s) => s.trim()).filter(Boolean);
    if (kws.join(",") !== prefs.keywords.join(",")) setPref("keywords", kws);
  };

  const areaLabel = (v: string) => meta?.areas.find((a) => a.value === v)?.label ?? v;
  const filters = [
    !prefs.include_rejected && t("rprefs.acceptedOnly"),
    prefs.venues.length > 0 && prefs.venues.map((v) => meta?.venues.find((x) => x.value === v)?.label ?? v).join(", "),
    prefs.year_from && t("rprefs.fromYear", { y: prefs.year_from }),
    prefs.only_with_code && t("rprefs.withCode"),
  ].filter(Boolean);

  return (
    <fieldset className="rprefs">
      <legend>{t("rprefs.title")}</legend>

      <label htmlFor="rp-fresh">{t("account.freshness")}</label>
      <input id="rp-fresh" type="range" min={0} max={1} step={0.1} value={prefs.freshness}
             onChange={(e) => setPref("freshness", Number(e.target.value))} />
      <div className="range-ends"><span>{t("account.classic")}</span><span>{t("account.newest")}</span></div>

      <label htmlFor="rp-div">{t("account.diversity")}</label>
      <input id="rp-div" type="range" min={0} max={1} step={0.1} value={prefs.diversity}
             onChange={(e) => setPref("diversity", Number(e.target.value))} />
      <div className="range-ends"><span>{t("account.focused")}</span><span>{t("account.diverse")}</span></div>

      <div className="rprefs-head">{t("account.areas")}</div>
      {prefs.areas.length === 0 && <div className="small muted">{t("rprefs.noAreas")}</div>}
      {prefs.areas.map((a) => (
        <label key={a} className="small">
          <input type="checkbox" checked onChange={() => setPref("areas", prefs.areas.filter((x) => x !== a))} />{" "}
          {areaLabel(a)}
        </label>
      ))}
      <select value="" aria-label={t("rprefs.addArea")}
              onChange={(e) => e.target.value && setPref("areas", [...prefs.areas, e.target.value])}>
        <option value="">{t("rprefs.addArea")}</option>
        {meta?.areas.filter((a) => !prefs.areas.includes(a.value)).map((a) => (
          <option key={a.value} value={a.value}>{a.label}</option>
        ))}
      </select>

      <label htmlFor="rp-kw" className="rprefs-head">{t("account.keywords")}</label>
      <input id="rp-kw" type="text" value={kwDraft} placeholder={t("account.keywordsPh")}
             onChange={(e) => setKwDraft(e.target.value)} onBlur={commitKeywords}
             onKeyDown={(e) => e.key === "Enter" && commitKeywords()} />

      <p className="small muted">
        {filters.length > 0 && <>{t("rprefs.filtering", { list: filters.join("; ") })} </>}
        <Link to="/account">{t("rprefs.more")}</Link>
      </p>
      <p className="small muted" aria-live="polite">
        {status === "saving" && t("rprefs.saving")}
        {status === "saved" && t("rprefs.saved")}
        {status === "error" && <span style={{ color: "var(--danger)" }}>{t("rprefs.error")}</span>}
      </p>
    </fieldset>
  );
}
