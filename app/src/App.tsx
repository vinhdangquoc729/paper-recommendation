import { Link, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import type { Lang } from "./i18n";
import { AccountPage } from "./pages/AccountPage";
import { LoginPage } from "./pages/LoginPage";
import { PaperPage } from "./pages/PaperPage";
import { PapersPage } from "./pages/PapersPage";
import { Theme, useI18n, usePrefs } from "./prefs";
import { useSession } from "./session";
import { useAsync } from "./useAsync";

export function App() {
  const meta = useAsync(() => api.meta(), []);
  const { t } = useI18n();
  const wide = useLocation().pathname.startsWith("/paper/");   // trang đọc bài cần rộng cho PDF

  return (
    <>
      <header className="masthead">
        <div className={wide ? "masthead-inner wide" : "masthead-inner"}>
          <Link to="/" className="brand">
            <img src="/scimate-icon.png" alt="SciMate" className="brand-logo" width={34} height={34} />
            <span>SciMate <small>{t("app.tagline")}</small></span>
          </Link>
          <nav className="nav">
            <NavLink to="/" end>{t("nav.papers")}</NavLink>
            <NavLink to="/account">{t("nav.account")}</NavLink>
          </nav>
          <SessionBox />
          <ViewerPrefs />
        </div>
      </header>

      <main className={wide ? "page wide" : "page"}>
        {meta.error && <p className="error">{t("app.apiError")} {meta.error}</p>}
        <Routes>
          <Route path="/" element={<PapersPage meta={meta.data} />} />
          <Route path="/paper/:id" element={<PaperPage />} />
          <Route path="/account" element={<AccountPage meta={meta.data} />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<p>{t("app.notFound")} <Link to="/">{t("app.home")}</Link></p>} />
        </Routes>
      </main>

      <footer className={wide ? "footer wide" : "footer"}>{t("app.footer")}</footer>
    </>
  );
}

/** Người đang đăng nhập và nút đăng xuất, hoặc liên kết tới màn đăng nhập. */
function SessionBox() {
  const { session, ready, logout } = useSession();
  const { t } = useI18n();
  const navigate = useNavigate();
  if (!ready) return null;
  if (!session.logged_in) {
    return <nav className="nav" style={{ marginLeft: 0 }}><NavLink to="/login">{t("session.login")}</NavLink></nav>;
  }
  return (
    <div className="session-box">
      <span className="who" title={session.openreview_id || session.email}>
        {session.display_name || session.email}
      </span>
      <button type="button" onClick={async () => { await logout(); navigate("/"); }}>{t("session.logout")}</button>
    </div>
  );
}

/** Chọn ngôn ngữ và giao diện sáng / tối ở thanh tiêu đề. */
function ViewerPrefs() {
  const { lang, setLang, theme, setTheme } = usePrefs();
  const { t } = useI18n();
  return (
    <div className="viewer-prefs">
      <div className="lang-switch" role="group" aria-label={t("prefs.language")}>
        {(["vi", "en"] as Lang[]).map((l) => (
          <button key={l} type="button" className={lang === l ? "on" : ""} aria-pressed={lang === l}
                  onClick={() => setLang(l)}>
            {l.toUpperCase()}
          </button>
        ))}
      </div>
      <select value={theme} onChange={(e) => setTheme(e.target.value as Theme)} aria-label={t("prefs.theme")}>
        <option value="system">{t("theme.system")}</option>
        <option value="light">{t("theme.light")}</option>
        <option value="dark">{t("theme.dark")}</option>
      </select>
    </div>
  );
}
