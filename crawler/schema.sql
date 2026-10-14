-- Hợp đồng dữ liệu đầu ra của module crawler (data/corpus.sqlite).
-- Bảng được dựng lại hoàn toàn từ data/raw/ mỗi lần chạy `python -m crawler load`.
-- Khoá chính của bài là S2 paperId; bài OpenReview được nối sang qua or_submissions.s2_paper_id.

DROP TABLE IF EXISTS papers;
CREATE TABLE papers (
    paper_id          TEXT PRIMARY KEY,   -- S2 paperId
    corpus_id         INTEGER,
    title             TEXT,
    title_norm        TEXT,
    abstract          TEXT,
    venue_key         TEXT,               -- iclr / neurips / tmlr
    edition           INTEGER,            -- năm hội nghị (từ DBLP, thiếu thì lấy năm S2)
    s2_year           INTEGER,
    pub_date          TEXT,               -- publicationDate của S2 (thường là ngày lên arXiv)
    avail_date        TEXT,               -- pub_date, thiếu thì lấy ngày mặc định của edition
    arxiv_id          TEXT,
    doi               TEXT,
    dblp              TEXT,
    citation_count    INTEGER,
    influential_citation_count INTEGER,
    reference_count   INTEGER,            -- số reference S2 công bố
    n_refs_returned   INTEGER,            -- số reference thực sự lấy được
    refs_status       TEXT                -- ok / elided / empty / not_found / NULL (chưa cào)
);

DROP TABLE IF EXISTS authors;
CREATE TABLE authors (
    author_id  TEXT PRIMARY KEY,          -- S2 authorId
    name       TEXT
);

DROP TABLE IF EXISTS paper_authors;
CREATE TABLE paper_authors (
    paper_id   TEXT,
    author_id  TEXT,
    position   INTEGER,
    PRIMARY KEY (paper_id, author_id)
);

-- Cạnh trích dẫn citing -> cited; cited_id NULL nếu S2 không phân giải được reference.
DROP TABLE IF EXISTS citations;
CREATE TABLE citations (
    citing_id  TEXT,
    cited_id   TEXT,
    cited_year INTEGER
);

-- Đặc trưng cạnh, chỉ có cho mẫu bài đã cào ở bước s2-edges.
DROP TABLE IF EXISTS citation_meta;
CREATE TABLE citation_meta (
    citing_id      TEXT,
    cited_id       TEXT,
    is_influential INTEGER,
    intents        TEXT,                  -- JSON list
    n_contexts     INTEGER,
    contexts       TEXT                   -- JSON list, dùng cho gán nhãn tay
);
DROP TABLE IF EXISTS citation_meta_papers;
CREATE TABLE citation_meta_papers (
    paper_id  TEXT PRIMARY KEY,
    elided    INTEGER,
    n_edges   INTEGER
);

DROP TABLE IF EXISTS or_submissions;
CREATE TABLE or_submissions (
    forum_id        TEXT PRIMARY KEY,
    venue_key       TEXT,
    edition         INTEGER,
    number          INTEGER,
    title           TEXT,
    title_norm      TEXT,
    abstract        TEXT,
    tldr            TEXT,
    keywords        TEXT,                 -- JSON list
    primary_area    TEXT,                 -- ICLR, NeurIPS 2024+, ICML 2025+; NULL ở venue khác
    code_url        TEXT,                 -- chỉ ICML 2025+ có trường link_to_code
    authors         TEXT,                 -- JSON list tên, rỗng nếu đang ẩn danh
    authorids       TEXT,                 -- JSON list, rỗng nếu đang ẩn danh
    venue           TEXT,
    venueid         TEXT,
    decision_raw    TEXT,
    decision        TEXT,                 -- accept_oral / accept_spotlight / accept_poster / accept / reject / withdrawn / desk_rejected / NULL
    decision_date   TEXT,                 -- ngày của note Decision; NULL nếu venue không công bố note này
    cdate           TEXT,
    odate           TEXT,
    pdate           TEXT,
    has_meta_review INTEGER,
    n_reviews       INTEGER,
    s2_paper_id     TEXT                  -- nối sang papers.paper_id theo tiêu đề chuẩn hoá
);

DROP TABLE IF EXISTS or_reviews;
CREATE TABLE or_reviews (
    review_id   TEXT PRIMARY KEY,
    forum_id    TEXT,
    rating      REAL,
    confidence  REAL,
    cdate       TEXT                      -- ngày review được tạo (dùng để cắt theo thời gian khi đánh giá)
);

-- Reference lấy từ .bbl trong source arXiv (bù cho bài S2 ẩn reference).
DROP TABLE IF EXISTS bbl_papers;
CREATE TABLE bbl_papers (
    arxiv_id   TEXT PRIMARY KEY,
    paper_id   TEXT,                      -- papers.paper_id
    status     TEXT,                      -- ok / no_bbl / pdf_only / unknown_format / http_xxx
    bytes      INTEGER,
    seconds    REAL,
    has_bib    INTEGER,
    n_items    INTEGER
);
DROP TABLE IF EXISTS bbl_refs;
CREATE TABLE bbl_refs (
    citing_id     TEXT,                   -- papers.paper_id
    idx           INTEGER,
    title         TEXT,
    title_norm    TEXT,
    ref_arxiv_id  TEXT,
    cited_id      TEXT,                   -- bài trong corpus nếu khớp được (arXiv ID, rồi tiêu đề)
    match_by      TEXT                    -- arxiv / title / NULL
);

-- Reference giữa các bài OpenReview (lấy từ .bbl arXiv), làm ground truth cho đánh giá
DROP TABLE IF EXISTS or_arxiv;
CREATE TABLE or_arxiv (
    forum_id   TEXT PRIMARY KEY,
    arxiv_id   TEXT,
    source     TEXT                       -- s2_paper (ghép S2 theo venue) / s2 / arxiv (tra theo tiêu đề)
);
DROP TABLE IF EXISTS or_refs;
CREATE TABLE or_refs (
    citing_forum  TEXT,                   -- or_submissions.forum_id của bài trích
    idx           INTEGER,
    ref_key       TEXT,                   -- khoá trong \cite
    title         TEXT,
    title_norm    TEXT,
    ref_arxiv_id  TEXT,
    cited_forum   TEXT,                   -- bài OpenReview được trích nếu khớp được, NULL nếu ngoài corpus
    match_by      TEXT,                   -- arxiv / title / NULL
    -- đặc trưng của lần trích (spec 5.2), từ các lệnh \cite trong .tex; NULL nếu không đọc được .tex
    has_cite_info INTEGER,                -- bài trích có đọc được .tex không
    n_mentions    INTEGER,                -- số lần \cite reference này
    n_sections    INTEGER,                -- số section khác nhau có nhắc
    in_intro      INTEGER,
    in_related    INTEGER,
    in_method     INTEGER,
    in_experiment INTEGER,
    appendix_only INTEGER,
    only_in_list  INTEGER,                -- mọi lần nhắc đều trong \cite có >= 4 khoá
    min_list_size INTEGER
);

CREATE INDEX idx_citations_citing ON citations(citing_id);
CREATE INDEX idx_citations_cited ON citations(cited_id);
CREATE INDEX idx_pa_author ON paper_authors(author_id);
CREATE INDEX idx_or_refs_citing ON or_refs(citing_forum);
CREATE INDEX idx_or_refs_cited ON or_refs(cited_forum);
