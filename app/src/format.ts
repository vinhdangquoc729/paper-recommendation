export const DECISION_LABELS: Record<string, string> = {
  accept_oral: "Oral",
  accept_spotlight: "Spotlight",
  accept_poster: "Poster",
  accept: "Accept",
  reject: "Reject",
  withdrawn: "Withdrawn",
  desk_rejected: "Desk reject",
};

export function decisionLabel(d: string | null): string {
  return d ? DECISION_LABELS[d] ?? d : "Chưa có kết quả";
}

export function isAccepted(d: string | null): boolean {
  return !!d && d.startsWith("accept");
}

const nf = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

export function signed(x: number | null): string {
  if (x === null) return "";
  return (x > 0 ? "+" : "") + nf.format(x);
}

export function decimal(x: number | null, digits = 2): string {
  if (x === null) return "";
  return x.toLocaleString("vi-VN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function authorsShort(authors: string[], max = 6): string {
  if (authors.length === 0) return "Tác giả ẩn danh";
  if (authors.length <= max) return authors.join(", ");
  return `${authors.slice(0, max).join(", ")} và ${authors.length - max} người khác`;
}

export function dateVi(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}
