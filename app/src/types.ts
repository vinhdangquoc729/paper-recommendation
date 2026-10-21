// Khớp với api/schemas.py

export type FeedbackAction =
  "interested" | "not_interested" | "cleared" | "saved" | "unsaved" | "clicked" | "open_pdf";
export type FeedbackState = "interested" | "not_interested";

/** Lý do gợi ý dạng mã + tham số; dịch bằng khoá "reason.<code>" trong i18n.ts. */
export interface Reason {
  code: string;
  params: Record<string, string | number>;
}

export interface PaperSummary {
  id: string;
  title: string;
  authors: string[];
  venue: string;
  year: number;
  decision: string | null;
  primary_area: string | null;
  tldr: string | null;
  abstract_snippet: string | null;
  has_code: boolean;
  n_ratings: number;
  rating_z: number | null;
  quality: number | null;
  first_seen: string | null;
  reasons: Reason[];
  score: number | null;
  saved: boolean;
  feedback: FeedbackState | null;
}

export interface PaperList {
  mode: "recommend" | "search";
  query: string;
  total: number;
  offset: number;
  items: PaperSummary[];
}

export interface PaperVersion {
  forum_id: string;
  venue: string;
  year: number;
  decision: string | null;
  url: string;
}

export interface ReviewSummary {
  n_reviews: number;
  ratings: number[];
  mean_rating: number | null;
  rating_z: number | null;
}

export interface PaperDetail extends PaperSummary {
  abstract: string | null;
  keywords: string[];
  code_url: string | null;
  openreview_url: string;
  pdf_url: string;
  pdf_cached: boolean;
  reviews: ReviewSummary;
  versions: PaperVersion[];
}

export interface Preferences {
  areas: string[];
  venues: string[];
  keywords: string[];
  year_from: number | null;
  include_rejected: boolean;
  only_with_code: boolean;
  freshness: number;
  diversity: number;
  auto_read: boolean;
}

export interface Profile {
  display_name: string;
  email: string;
  openreview_id: string;   // chỉ đọc: gắn với tài khoản tác giả
  preferences: Preferences;
}

export type ProfileRole = "authored" | "cited" | "saved" | "interested" | "read";

/** Một bài trong hồ sơ mà bộ gợi ý đang dùng, kèm trọng số thật. */
export interface ProfilePaper {
  paper: PaperSummary;
  roles: ProfileRole[];
  weight: number;
}

export interface SessionInfo {
  logged_in: boolean;
  display_name: string;
  openreview_id: string;   // rỗng nếu tài khoản không gắn với tác giả nào
  email: string;
}

export interface AuthorHit {
  openreview_id: string;
  name: string;
  n_papers: number;
}

export interface AuthoredPaper {
  paper: PaperSummary;
  confirmed: boolean;
}

export interface Facet {
  value: string;
  label: string;
  count: number;
}

export interface Meta {
  venues: Facet[];
  years: number[];
  areas: Facet[];
  decisions: Facet[];
}

export interface PaperFilters {
  venue?: string;
  year?: number;
  decision?: string;
  has_code?: boolean;
}
