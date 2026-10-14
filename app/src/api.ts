// Lớp gọi API duy nhất của frontend: đổi backend thì chỉ sửa file này.
import type {
  AuthoredPaper, FeedbackAction, Meta, PaperDetail, PaperFilters, PaperList, PaperSummary, Profile,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfterS: number | null = null) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    let detail = body.slice(0, 200);
    try {
      detail = JSON.parse(body).detail ?? detail;   // FastAPI trả {"detail": "..."}
    } catch {
      /* giữ nguyên nội dung gốc */
    }
    const retry = Number(res.headers.get("Retry-After"));
    throw new ApiError(res.status, String(detail), Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") q.set(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const api = {
  meta: () => request<Meta>("/meta"),

  /** q rỗng: gợi ý theo hồ sơ; có q: tìm theo từ khoá. */
  papers: (q: string, filters: PaperFilters, offset: number, limit: number) =>
    request<PaperList>(`/papers${query({ q, ...filters, offset, limit })}`),

  paper: (id: string) => request<PaperDetail>(`/papers/${encodeURIComponent(id)}`),

  related: (id: string, limit = 10) =>
    request<PaperSummary[]>(`/papers/${encodeURIComponent(id)}/related${query({ limit })}`),

  /** Tải PDF về cache của backend (tốn 1 lượt OpenReview nếu chưa có). Lỗi 429 khi hết lượt trong giờ. */
  preparePdf: (id: string) => request<void>(`/papers/${encodeURIComponent(id)}/pdf`, { method: "POST" }),

  /** Đường dẫn PDF đã cache, dùng làm src của iframe. */
  pdfUrl: (id: string) => `/api/papers/${encodeURIComponent(id)}/pdf`,

  me: () => request<Profile>("/me"),

  saveMe: (profile: Profile) => request<Profile>("/me", { method: "PUT", body: JSON.stringify(profile) }),

  authored: () => request<AuthoredPaper[]>("/me/authored"),

  confirmAuthored: (paperId: string, confirmed: boolean) =>
    request<AuthoredPaper>(`/me/authored/${encodeURIComponent(paperId)}`, {
      method: "PUT",
      body: JSON.stringify({ confirmed }),
    }),

  saved: () => request<PaperSummary[]>("/me/saved"),

  feedback: (paperId: string, action: FeedbackAction) =>
    request<void>("/feedback", { method: "POST", body: JSON.stringify({ paper_id: paperId, action }) }),
};
