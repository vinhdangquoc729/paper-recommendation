// Lựa chọn của người xem (ngôn ngữ, giao diện sáng/tối), nhớ trong localStorage của trình duyệt.
import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { DECISION_LABELS } from "./format";
import { Lang, MessageKey, Params, translate } from "./i18n";

export type Theme = "system" | "light" | "dark";

const LANG_KEY = "paperrec.lang";
const THEME_KEY = "paperrec.theme";

function readStored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return allowed.includes(v as T) ? (v as T) : fallback;
  } catch {
    return fallback;   // chế độ riêng tư / chặn lưu trữ: vẫn chạy bình thường
  }
}

function store(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* bỏ qua: chỉ là tiện ích, không bắt buộc */
  }
}

interface Prefs {
  lang: Lang;
  setLang: (l: Lang) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const PrefsContext = createContext<Prefs | null>(null);

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() =>
    readStored(LANG_KEY, ["vi", "en"] as const, navigator.language.startsWith("vi") ? "vi" : "en"));
  const [theme, setThemeState] = useState<Theme>(() => readStored(THEME_KEY, ["system", "light", "dark"] as const, "system"));

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  useEffect(() => {
    // "system": bỏ data-theme để CSS theo prefers-color-scheme
    if (theme === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
  }, [theme]);

  const value = useMemo<Prefs>(() => ({
    lang,
    setLang: (l) => { setLangState(l); store(LANG_KEY, l); },
    theme,
    setTheme: (t) => { setThemeState(t); store(THEME_KEY, t); },
  }), [lang, theme]);

  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): Prefs {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs phải nằm trong PrefsProvider");
  return ctx;
}

/** Hàm dịch và định dạng theo ngôn ngữ đang chọn. */
export function useI18n() {
  const { lang } = usePrefs();
  return useMemo(() => {
    const locale = lang === "vi" ? "vi-VN" : "en-US";
    const t = (key: MessageKey, params?: Params) => translate(lang, key, params);
    const decimal = (x: number | null, digits = 2) =>
      x === null ? "" : x.toLocaleString(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });
    return {
      lang,
      t,
      int: (n: number) => n.toLocaleString(locale),
      decimal,
      signed: (x: number | null) => (x === null ? "" : (x > 0 ? "+" : "") + decimal(x)),
      date: (iso: string | null) =>
        iso ? new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString(locale,
          { day: "2-digit", month: lang === "vi" ? "2-digit" : "short", year: "numeric" }) : "",
      time: (d: Date) => d.toLocaleTimeString(locale),
      decision: (d: string | null) => (d ? DECISION_LABELS[d] ?? d : t("decision.none")),
      authors: (list: string[], max = 6) => {
        if (list.length === 0) return t("authors.anonymous");
        if (list.length <= max) return list.join(", ");
        return t("authors.more", { list: list.slice(0, max).join(", "), n: list.length - max });
      },
    };
  }, [lang]);
}
