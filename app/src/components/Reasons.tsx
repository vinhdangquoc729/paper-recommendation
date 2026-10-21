import type { MessageKey } from "../i18n";
import { useI18n } from "../prefs";
import type { Reason } from "../types";
import { plainTex } from "./Tex";

/** Dịch một lý do gợi ý; mã chưa có trong từ điển thì hiện nguyên mã. */
export function useReasonText() {
  const { t } = useI18n();
  return (r: Reason) => {
    const key = `reason.${r.code}` as MessageKey;
    const params = r.params?.title ? { ...r.params, title: plainTex(String(r.params.title)) } : r.params;
    const text = t(key, params);
    return text === key ? r.code : text;
  };
}

export function Reasons({ reasons }: { reasons: Reason[] }) {
  const { t } = useI18n();
  const text = useReasonText();
  if (reasons.length === 0) return null;
  return (
    <div className="paper-reasons">
      <b>{t("row.why")}</b> {reasons.map(text).join("; ")}
    </div>
  );
}
