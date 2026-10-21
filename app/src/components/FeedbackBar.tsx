import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import type { MessageKey } from "../i18n";
import { useI18n } from "../prefs";
import { useSession } from "../session";
import type { FeedbackAction, FeedbackState, PaperSummary } from "../types";

const STATE_BUTTONS: { action: FeedbackState; label: MessageKey; title: MessageKey }[] = [
  { action: "interested", label: "fb.interested", title: "fb.interestedTitle" },
  { action: "not_interested", label: "fb.notInterested", title: "fb.notInterestedTitle" },
];

/** Lưu / Quan tâm / Không quan tâm cho một bài ("đã đọc" tự ghi khi mở trang bài). Bấm lại nút đang bật để bỏ chọn.
 *  Cập nhật lạc quan, báo lỗi nếu gửi thất bại. */
export function FeedbackBar({ paper }: { paper: PaperSummary }) {
  const { t } = useI18n();
  const { session } = useSession();
  const [needLogin, setNeedLogin] = useState(false);
  const [saved, setSaved] = useState(paper.saved);
  const [state, setState] = useState<FeedbackState | null>(paper.feedback);
  const [error, setError] = useState<string | null>(null);

  const send = async (action: FeedbackAction, undo: () => void) => {
    setError(null);
    if (!session.logged_in) {
      undo();
      setNeedLogin(true);
      return;
    }
    try {
      await api.feedback(paper.id, action);
    } catch (e) {
      undo();
      setError((e as Error).message);
    }
  };

  const toggleSave = () => {
    const next = !saved;
    setSaved(next);
    send(next ? "saved" : "unsaved", () => setSaved(!next));
  };

  const choose = (action: FeedbackState) => {
    const prev = state;
    const next = prev === action ? null : action;
    setState(next);
    send(next ?? "cleared", () => setState(prev));
  };

  return (
    <div className="actions">
      <button className={saved ? "on" : ""} onClick={toggleSave} title={t("fb.saveTitle")}>
        {saved ? t("fb.saved") : t("fb.save")}
      </button>
      {STATE_BUTTONS.map((b) => (
        <button key={b.action} className={state === b.action ? "on" : ""} title={t(b.title)}
                aria-pressed={state === b.action} onClick={() => choose(b.action)}>
          {t(b.label)}
        </button>
      ))}
      {error && <span className="small" style={{ color: "var(--danger)" }}>{error}</span>}
      {needLogin && (
        <span className="small muted">{t("fb.needLogin")} <Link to="/login">{t("session.login")}</Link></span>
      )}
    </div>
  );
}
