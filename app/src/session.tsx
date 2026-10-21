// Trạng thái đăng nhập dùng chung cho mọi màn. Phiên thật nằm ở cookie httponly của backend.
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { SessionInfo } from "./types";

const ANONYMOUS: SessionInfo = { logged_in: false, display_name: "", openreview_id: "", email: "" };

interface Session {
  session: SessionInfo;
  ready: boolean;                       // đã hỏi backend xong lần đầu
  setSession: (s: SessionInfo) => void; // sau khi đăng nhập / đăng ký
  logout: () => Promise<void>;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo>(ANONYMOUS);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api.session().then(setSession).catch(() => setSession(ANONYMOUS)).finally(() => setReady(true));
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setSession(ANONYMOUS);
  }, []);

  const value = useMemo(() => ({ session, ready, setSession, logout }), [session, ready, logout]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession phải nằm trong SessionProvider");
  return ctx;
}
