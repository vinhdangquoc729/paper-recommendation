// Khớp với api/schemas.py

export type FeedbackAction = "relevant" | "not_relevant" | "already_read" | "saved" | "unsaved" | "clicked";

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
  feedback: FeedbackAction | null;
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
}

export interface Profile {
  display_name: string;
  email: string;
  openreview_id: string;
  preferences: Preferences;
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
