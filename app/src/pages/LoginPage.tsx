import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useI18n } from "../prefs";
import { useSession } from "../session";
import type { AuthorHit } from "../types";

/** Đăng nhập: chọn một tác giả có sẵn trong dữ liệu (bản demo), hoặc tài khoản email + mật khẩu. */
export function LoginPage() {
  const { t } = useI18n();
  const { session, logout } = useSession();

  return (
    <>
      <h1>{t("login.title")}</h1>
      {session.logged_in && (
        <p className="muted">
          {t("login.already", { name: session.display_name || session.email })}{" "}
          <button onClick={logout}>{t("session.logout")}</button>
        </p>
      )}
      <AuthorLogin />
      <EmailLogin />
    </>
  );
}

function AuthorLogin() {
  const { t, int } = useI18n();
  const { setSession } = useSession();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<AuthorHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (q.trim().length < 2) {
      setHits(null);
      return;
    }
    const timer = setTimeout(() => {
      api.searchAuthors(q).then(setHits).catch((e) => setError((e as Error).message));
    }, 250);
    return () => clearTimeout(timer);
  }, [q]);

  const enter = async (id: string) => {
    setError(null);
    try {
      setSession(await api.loginAsAuthor(id));
      navigate("/");
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <fieldset>
      <legend>{t("login.asAuthor")}</legend>
      <p className="small muted" style={{ marginTop: 0 }}>{t("login.asAuthorHint")}</p>
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("login.authorPh")}
             aria-label={t("login.authorPh")} style={{ width: "100%", maxWidth: 420 }} />
      {error && <p className="error">{error}</p>}
      {hits && hits.length === 0 && <p className="muted small">{t("login.noAuthor")}</p>}
      {hits && hits.length > 0 && (
        <table className="grid" style={{ marginTop: 8 }}>
          <thead>
            <tr><th>{t("login.colAuthor")}</th><th>OpenReview ID</th><th>{t("login.colPapers")}</th><th /></tr>
          </thead>
          <tbody>
            {hits.map((a) => (
              <tr key={a.openreview_id}>
                <td>{a.name}</td>
                <td className="small">{a.openreview_id}</td>
                <td>{int(a.n_papers)}</td>
                <td className="center"><button onClick={() => enter(a.openreview_id)}>{t("login.enter")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </fieldset>
  );
}

function EmailLogin() {
  const { t } = useI18n();
  const { setSession } = useSession();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      setSession(mode === "login" ? await api.login(email, password) : await api.register(email, password, name));
      navigate(mode === "login" ? "/" : "/account");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <fieldset>
      <legend>{t("login.email")}</legend>
      <div className="actions" role="group" style={{ marginBottom: 10 }}>
        <button type="button" className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>
          {t("login.signIn")}
        </button>
        <button type="button" className={mode === "register" ? "on" : ""} onClick={() => setMode("register")}>
          {t("login.signUp")}
        </button>
      </div>
      <form className="form-grid" onSubmit={submit}>
        {mode === "register" && (
          <>
            <label htmlFor="reg-name">{t("account.name")}</label>
            <input id="reg-name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
          </>
        )}
        <label htmlFor="login-email">{t("account.email")}</label>
        <input id="login-email" type="email" value={email} required autoComplete="email"
               onChange={(e) => setEmail(e.target.value)} />
        <label htmlFor="login-pw">{t("login.password")}</label>
        <input id="login-pw" type="password" value={password} required minLength={mode === "register" ? 8 : undefined}
               autoComplete={mode === "login" ? "current-password" : "new-password"}
               onChange={(e) => setPassword(e.target.value)} />
        {mode === "register" && <div className="hint">{t("login.signUpHint")}</div>}
        <span />
        <div>
          <button type="submit" className="primary" disabled={busy}>
            {mode === "login" ? t("login.signIn") : t("login.signUp")}
          </button>
          {error && <span className="small" style={{ color: "var(--danger)", marginLeft: 10 }}>{error}</span>}
        </div>
      </form>
    </fieldset>
  );
}
