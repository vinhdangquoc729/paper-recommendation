import { useState } from "react";
import { api } from "../api";
import type { FeedbackAction, PaperSummary } from "../types";

const STATE_BUTTONS: { action: FeedbackAction; label: string; title: string }[] = [
  { action: "relevant", label: "Liên quan", title: "Gợi ý thêm những bài giống bài này" },
  { action: "not_relevant", label: "Không liên quan", title: "Không gợi ý bài này và bớt những bài tương tự" },
  { action: "already_read", label: "Đã đọc", title: "Đánh dấu đã đọc, không gợi ý lại" },
];

/** Các nút phản hồi cho một bài. Cập nhật lạc quan, báo lỗi nếu gửi thất bại. */
export function FeedbackBar({ paper }: { paper: PaperSummary }) {
  const [saved, setSaved] = useState(paper.saved);
  const [state, setState] = useState<FeedbackAction | null>(paper.feedback);
  const [error, setError] = useState<string | null>(null);

  const send = async (action: FeedbackAction, undo: () => void) => {
    setError(null);
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

  const choose = (action: FeedbackAction) => {
    const prev = state;
    setState(action);
    send(action, () => setState(prev));
  };

  return (
    <div className="actions">
      <button className={saved ? "on" : ""} onClick={toggleSave} title="Lưu vào thư viện của bạn">
        {saved ? "Đã lưu" : "Lưu"}
      </button>
      {STATE_BUTTONS.map((b) => (
        <button key={b.action} className={state === b.action ? "on" : ""} title={b.title} onClick={() => choose(b.action)}>
          {b.label}
        </button>
      ))}
      {error && <span className="small" style={{ color: "var(--danger)" }}>{error}</span>}
    </div>
  );
}
