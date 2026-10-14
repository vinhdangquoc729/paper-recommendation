// Nhãn decision giữ nguyên tiếng Anh ở cả hai ngôn ngữ (thuật ngữ của hội nghị).
// Các hàm định dạng theo ngôn ngữ nằm trong useI18n() (prefs.tsx).
export const DECISION_LABELS: Record<string, string> = {
  accept_oral: "Oral",
  accept_spotlight: "Spotlight",
  accept_poster: "Poster",
  accept: "Accept",
  reject: "Reject",
  withdrawn: "Withdrawn",
  desk_rejected: "Desk reject",
};

export function isAccepted(d: string | null): boolean {
  return !!d && d.startsWith("accept");
}
