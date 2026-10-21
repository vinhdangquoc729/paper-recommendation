-- Lược đồ ban đầu (spec mục 3). Hai phần:
-- 1. Catalog: chỉ lệnh `python -m appdb sync` ghi, nạp lại cả lô từ đầu ra của crawler / features.
-- 2. Người dùng: API ghi. Bảng người dùng KHÔNG có khoá ngoại tới papers, vì sync thay toàn bộ catalog;
--    sync ánh xạ lại paper_id cũ qua paper_versions khi bài được gộp khác đi.
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- Catalog ----------
CREATE TABLE catalog_meta (
    id          INT PRIMARY KEY CHECK (id = 1),
    version     TEXT NOT NULL,          -- thời điểm sync, API nạp lại khi đổi
    synced_at   TIMESTAMPTZ NOT NULL,
    n_papers    INT NOT NULL
);

CREATE TABLE papers (
    id            TEXT PRIMARY KEY,     -- item_id của features: forum_id của bản đại diện
    venue         TEXT NOT NULL,        -- iclr / icml / neurips / tmlr
    edition       INT NOT NULL,
    title         TEXT NOT NULL,
    abstract      TEXT,
    tldr          TEXT,
    keywords      JSONB NOT NULL DEFAULT '[]',
    primary_area  TEXT,
    code_url      TEXT,
    author_names  JSONB NOT NULL DEFAULT '[]',
    decision      TEXT,
    decision_date DATE,
    first_seen    DATE,                 -- ngày công khai sớm nhất trong các lần nộp
    n_versions    INT NOT NULL DEFAULT 1,
    is_candidate  BOOLEAN NOT NULL,     -- accept / reject; withdrawn, desk-reject, đang review thì không gợi ý
    n_ratings     INT NOT NULL DEFAULT 0,
    rating_z      REAL,
    quality       REAL,                 -- q_p (spec 6.3)
    arxiv_id      TEXT,
    embedding     vector(768)           -- SPECTER2, đã chuẩn hoá L2
);
CREATE INDEX papers_first_seen ON papers (first_seen);

CREATE TABLE paper_versions (
    forum_id      TEXT PRIMARY KEY,     -- mọi lần nộp trên OpenReview
    paper_id      TEXT NOT NULL REFERENCES papers ON DELETE CASCADE,
    venue         TEXT NOT NULL,
    edition       INT NOT NULL,
    decision      TEXT,
    avail_date    DATE
);
CREATE INDEX paper_versions_paper ON paper_versions (paper_id);

CREATE TABLE authors (
    id            SERIAL PRIMARY KEY,
    openreview_id TEXT NOT NULL UNIQUE, -- ~Ten_Ho1; giữ nguyên qua các lần sync (users trỏ tới)
    name          TEXT
);
CREATE INDEX authors_name ON authors (lower(name));

CREATE TABLE paper_authors (
    paper_id      TEXT NOT NULL REFERENCES papers ON DELETE CASCADE,
    author_id     INT NOT NULL REFERENCES authors,
    position      INT NOT NULL,         -- 0 = tác giả đầu
    PRIMARY KEY (paper_id, author_id)
);
CREATE INDEX paper_authors_author ON paper_authors (author_id);

-- Cạnh trích dẫn giữa hai bài trong corpus, kèm ngữ cảnh trích (or_refs). Trọng số w(p, r) tính lúc nạp vào bộ nhớ
-- (features.reference_filter) để đổi hệ số mà không phải sync lại.
CREATE TABLE citations (
    citing_id     TEXT NOT NULL REFERENCES papers ON DELETE CASCADE,
    cited_id      TEXT NOT NULL REFERENCES papers ON DELETE CASCADE,
    has_cite_info BOOLEAN NOT NULL,
    n_mentions    INT,
    in_method     BOOLEAN,
    in_experiment BOOLEAN,
    only_in_list  BOOLEAN,
    appendix_only BOOLEAN,
    PRIMARY KEY (citing_id, cited_id)
);
CREATE INDEX citations_cited ON citations (cited_id);

-- Bài lấy được reference (kể cả khi không reference nào nằm trong corpus): phân biệt "không trích ai" với "không biết"
CREATE TABLE papers_with_refs (
    paper_id      TEXT PRIMARY KEY REFERENCES papers ON DELETE CASCADE
);

CREATE TABLE reviews (
    forum_id      TEXT NOT NULL,
    paper_id      TEXT NOT NULL REFERENCES papers ON DELETE CASCADE,
    rating        REAL,
    confidence    REAL
);
CREATE INDEX reviews_paper ON reviews (paper_id);

-- ---------- Người dùng ----------
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    author_id     INT UNIQUE REFERENCES authors,   -- danh tính OpenReview; NULL với người chưa có bài
    email         TEXT UNIQUE,
    password_hash TEXT,
    display_name  TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('seeded', 'active')),
    preferences   JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE sessions (
    token         TEXT PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES users ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL
);

-- Trạng thái hiện tại của quan hệ người dùng - bài (suy từ events):
--   authored: chỉ lưu phần người dùng sửa so với OpenReview (confirmed = false: "không phải bài của tôi";
--             source = manual: tự thêm); bài trong paper_authors mặc định là của họ
--   saved / read: bài đã lưu, đã đọc
CREATE TABLE user_papers (
    user_id       INT NOT NULL REFERENCES users ON DELETE CASCADE,
    paper_id      TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('authored', 'saved', 'read')),
    confirmed     BOOLEAN NOT NULL DEFAULT TRUE,
    source        TEXT NOT NULL DEFAULT 'app',
    event_time    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, paper_id, role)
);

-- Nhật ký thao tác, chỉ ghi thêm: impression / click / open_pdf / saved / unsaved / relevant / not_relevant /
-- already_read. Dùng để dựng lại user_papers, cập nhật hồ sơ và đo online (tỉ lệ click, lưu).
CREATE TABLE events (
    id            BIGSERIAL PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES users ON DELETE CASCADE,
    paper_id      TEXT,
    type          TEXT NOT NULL,
    context       JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX events_user ON events (user_id, created_at);

-- Mỗi lần gợi ý: để tránh lặp, hiển thị lời giải thích và đo "đã gợi ý thì có bấm không"
CREATE TABLE rec_runs (
    id            BIGSERIAL PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES users ON DELETE CASCADE,
    mode          TEXT NOT NULL,
    model         TEXT NOT NULL,
    catalog_version TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX rec_runs_user ON rec_runs (user_id, created_at);

CREATE TABLE rec_items (
    run_id        BIGINT NOT NULL REFERENCES rec_runs ON DELETE CASCADE,
    rank          INT NOT NULL,
    paper_id      TEXT NOT NULL,
    score         REAL,
    score_parts   JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, rank)
);
