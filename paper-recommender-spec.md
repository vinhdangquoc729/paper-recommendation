# Đặc tả triển khai: Hệ gợi ý bài báo khoa học

> Tài liệu này mô tả bài toán, dữ liệu, thuật toán, tính năng, kiến trúc, đánh giá và lộ trình triển khai.

---

## Mục lục

1. [Bài toán và mục tiêu](#1-bài-toán-và-mục-tiêu)
2. [Nguồn dữ liệu](#2-nguồn-dữ-liệu)
3. [Lược đồ dữ liệu](#3-lược-đồ-dữ-liệu)
4. [Tổng quan pipeline](#4-tổng-quan-pipeline)
5. [Khối 1: Thu thập và làm sạch reference](#5-khối-1-thu-thập-và-làm-sạch-reference)
6. [Khối 2: Biểu diễn bài báo](#6-khối-2-biểu-diễn-bài-báo)
7. [Khối 3: Hồ sơ người dùng ("mình là ai")](#7-khối-3-hồ-sơ-người-dùng-mình-là-ai)
8. [Khối 4: Sinh ứng viên](#8-khối-4-sinh-ứng-viên)
9. [Khối 5: Xếp hạng](#9-khối-5-xếp-hạng)
10. [Khối 6: Xếp hạng lại, lọc và giải thích](#10-khối-6-xếp-hạng-lại-lọc-và-giải-thích)
11. [Khối 7: Vòng phản hồi](#11-khối-7-vòng-phản-hồi)
12. [Đánh giá](#12-đánh-giá)
13. [Tính năng phần mềm](#13-tính-năng-phần-mềm)
14. [Kiến trúc hệ thống và công nghệ](#14-kiến-trúc-hệ-thống-và-công-nghệ)
15. [API backend](#15-api-backend)
16. [Lộ trình và phân công](#16-lộ-trình-và-phân-công)
17. [Rủi ro và lưu ý](#17-rủi-ro-và-lưu-ý)
18. [Phụ lục: tham số mặc định](#18-phụ-lục-tham-số-mặc-định)

---

## 1. Bài toán và mục tiêu

Gợi ý cho nhà nghiên cứu những bài báo **liên quan**, **mới** và **có giá trị**, dựa trên lịch sử công bố và đọc của chính họ.

### Ba vấn đề cần giải quyết 

| # | Vấn đề | Hướng giải quyết | Khối liên quan |
|---|---|---|---|
| V1 | **Tính mới**: các hệ hiện có gửi digest hằng tuần nhưng phần lớn là bài cũ | Tách pool ứng viên theo thời gian; content-based cho bài chưa có tương tác; time decay; loại bài người dùng đã biết | 4, 5, 6 |
| V2 | **Tính hữu ích / chất lượng**: bài ít giá trị vẫn được gợi ý liên tục | Điểm chất lượng từ review, decision, citation velocity; dùng làm thành phần re-ranking | 2, 5 |
| V3 | **Reference nhiễu**: nhiều reference không thực sự liên quan | Trọng số hoá cạnh trích dẫn theo intent, vị trí, tần suất, độ tương đồng nội dung; giảm trọng số hub | 1 |

### Giả định về người dùng

Người dùng có thể khai báo **"mình là ai"**: liên kết danh tính tác giả (OpenReview / Semantic Scholar), từ đó hệ dựng hồ sơ từ các bài họ đã viết, đã trích và đã đọc.

### Phạm vi

- Lĩnh vực: ML / AI (theo phạm vi dữ liệu OpenReview).
- Venue đề xuất: ICLR 2023–2026, NeurIPS 2023–2025, TMLR.

---

## 2. Nguồn dữ liệu

| Nguồn | Lấy gì | Cách lấy | Vai trò |
|---|---|---|---|
| **OpenReview** (nguồn chính) | submission (title, abstract, keywords, TL;DR, tác giả, thời gian), PDF, review (rating, confidence), meta-review, decision, profile tác giả | API v2 qua `openreview-py`, endpoint `https://api2.openreview.net` | nội dung, chất lượng, danh tính |
| **Semantic Scholar** | reference, citation, `isInfluential`, citation intents, embedding SPECTER2, author ID | Semantic Scholar Graph API (nên xin API key) | đồ thị trích dẫn, lọc reference |
| **GROBID** (dự phòng) | reference + vị trí trích dẫn trong toàn văn | chạy Docker, parse PDF | khi Semantic Scholar không tra được bài |
| **arXiv** (tuỳ chọn) | bài mới hằng ngày | arXiv API / OAI-PMH | mở rộng luồng bài mới |

### Lưu ý khi thu thập

- Mọi đối tượng trên OpenReview đều là **note**; review và decision là các note trả lời bài nộp. Lấy bằng `get_all_notes(invitation=..., details="directReplies")`.
- Bài accept mang venue id gốc; reject / withdrawn có id riêng trong venue group.
- Tên trường (`rating`, `decision`, …) và tên invitation **khác nhau giữa venue và năm**. In thử một note mỗi venue trước khi viết parser chung.
- Mức công khai khác nhau: có venue công khai review của cả bài reject, có venue chỉ công khai bài accept. Ghi lại trong bảng `venues`.
- Không có rate limit công bố rõ: phân trang, nghỉ khoảng 0,5 s giữa các request, có retry và exponential backoff, lưu cache vào DB để không cào lại.
- Reference: **thử Semantic Scholar trước** (tra theo arXiv ID → DOI → title), chỉ dùng GROBID khi không tra được.

### Code mẫu thu thập

```python
import openreview, time

client = openreview.api.OpenReviewClient(baseurl="https://api2.openreview.net")

def fetch_venue(venue_id: str):
    subs = client.get_all_notes(invitation=f"{venue_id}/-/Submission",
                                details="directReplies")
    for note in subs:
        c = note.content
        paper = {
            "openreview_id": note.id,
            "title": c["title"]["value"],
            "abstract": c["abstract"]["value"],
            "keywords": c.get("keywords", {}).get("value", []),
            "authorids": c.get("authorids", {}).get("value", []),
            "venueid": c.get("venueid", {}).get("value"),
            "pdate": note.pdate or note.cdate,
        }
        reviews, decision = [], None
        for r in note.details.get("directReplies", []):
            inv = r["invitations"][0]
            if inv.endswith("Official_Review"):
                reviews.append({
                    "rating": r["content"].get("rating", {}).get("value"),
                    "confidence": r["content"].get("confidence", {}).get("value"),
                })
            elif inv.endswith("Decision"):
                decision = r["content"]["decision"]["value"]
        yield paper, reviews, decision

def fetch_author_papers(profile_id: str):
    return client.get_all_notes(content={"authorids": profile_id})
```

---

## 3. Lược đồ dữ liệu

Đề xuất PostgreSQL + extension `pgvector` (hoặc lưu embedding riêng và dùng FAISS).

```sql
-- Bài báo
papers (
  id              SERIAL PRIMARY KEY,
  openreview_id   TEXT UNIQUE,
  s2_id           TEXT,               -- Semantic Scholar paper ID
  arxiv_id        TEXT,
  title           TEXT,
  abstract        TEXT,
  keywords        TEXT[],
  venue_id        TEXT,
  year            INT,
  pub_date        TIMESTAMP,
  decision        TEXT,               -- accept_oral / accept_spotlight / accept_poster / reject / withdrawn / unknown
  has_code        BOOLEAN,
  in_corpus       BOOLEAN,            -- true: bài có đủ dữ liệu; false: chỉ là reference ngoài corpus
  embedding       VECTOR(768),        -- SPECTER2
  quality_score   REAL,
  citation_count  INT,
  updated_at      TIMESTAMP
)

venues (
  venue_id        TEXT PRIMARY KEY,
  name            TEXT,
  year            INT,
  rating_scale    TEXT,               -- mô tả thang điểm
  public_rejected BOOLEAN             -- có công khai review bài reject không
)

reviews (
  id          SERIAL PRIMARY KEY,
  paper_id    INT REFERENCES papers,
  rating      REAL,
  confidence  REAL,
  rating_z    REAL                    -- đã chuẩn hoá theo venue-năm
)

authors (
  id              SERIAL PRIMARY KEY,
  openreview_id   TEXT UNIQUE,        -- ~Nguyen_Van_A1
  s2_author_id    TEXT,
  name            TEXT
)

paper_authors (
  paper_id   INT REFERENCES papers,
  author_id  INT REFERENCES authors,
  position   INT                      -- 0 = tác giả đầu
)

-- Cạnh trích dẫn citing -> cited, kèm các đặc trưng để lọc
citations (
  citing_id      INT REFERENCES papers,
  cited_id       INT REFERENCES papers,
  is_influential BOOLEAN,
  intents        TEXT[],              -- background / methodology / result
  mention_count  INT,                 -- số lần nhắc trong toàn văn (GROBID)
  sections       TEXT[],              -- intro / related_work / method / experiments
  content_sim    REAL,                -- cos(e_citing, e_cited)
  weight         REAL,                -- w(p, r) sau khi lọc
  PRIMARY KEY (citing_id, cited_id)
)

-- Láng giềng tính sẵn (top-k)
paper_neighbors (
  paper_id     INT,
  neighbor_id  INT,
  kind         TEXT,                  -- content / coupling / cocitation
  score        REAL,
  PRIMARY KEY (paper_id, neighbor_id, kind)
)

-- Người dùng
users (
  id                  SERIAL PRIMARY KEY,
  email               TEXT,
  author_id           INT REFERENCES authors,   -- danh tính đã liên kết, có thể NULL
  settings            JSONB,                    -- tần suất digest, trọng số, bật/tắt mục
  created_at          TIMESTAMP
)

user_papers (
  user_id     INT REFERENCES users,
  paper_id    INT REFERENCES papers,
  role        TEXT,                   -- authored / cited / read / saved
  weight      REAL,
  event_time  TIMESTAMP,
  confirmed   BOOLEAN,                -- người dùng đã xác nhận (với authored)
  PRIMARY KEY (user_id, paper_id, role)
)

interest_clusters (
  id          SERIAL PRIMARY KEY,
  user_id     INT REFERENCES users,
  label       TEXT,                   -- tự sinh từ keywords, người dùng đổi được
  centroid    VECTOR(768),
  weight      REAL,                   -- người dùng tăng/giảm
  muted       BOOLEAN
)

feedback (
  user_id     INT,
  paper_id    INT,
  action      TEXT,                   -- relevant / not_relevant / already_read / less_like_this / saved / clicked
  context     JSONB,                  -- màn hình, vị trí trong danh sách, recommendation_id
  created_at  TIMESTAMP
)

recommendation_log (
  id             SERIAL PRIMARY KEY,
  user_id        INT,
  paper_id       INT,
  mode           TEXT,                -- digest / foundational / explore / similar
  rank           INT,
  score_parts    JSONB,               -- {rel, quality, fresh, graph, ...}
  sources        TEXT[],              -- content / coupling / cocitation / coauthor / cites_me
  explanation    TEXT,
  created_at     TIMESTAMP
)
```

---

## 4. Tổng quan pipeline

```
┌─────────────────┐   ┌──────────────────────┐   ┌─────────────────────┐
│ 1. Thu thập &   │──►│ 2. Biểu diễn bài báo │──►│ 3. Hồ sơ người dùng │
│ lọc reference   │   │ embedding / đồ thị / │   │ đa sở thích         │
│                 │   │ chất lượng           │   │                     │
└─────────────────┘   └──────────────────────┘   └──────────┬──────────┘
                                                            │
┌─────────────────┐   ┌──────────────────────┐   ┌──────────▼──────────┐
│ 7. Phản hồi     │◄──│ 6. Re-ranking, lọc,  │◄──│ 4. Sinh ứng viên    │
│                 │   │ giải thích           │   │ (nhiều nguồn)       │
└────────┬────────┘   └──────────▲───────────┘   └──────────┬──────────┘
         │                       │                          │
         │                       └──── 5. Xếp hạng ◄────────┘
         └──────► cập nhật hồ sơ (3)
```

Phân chia **offline** và **online**:

| Offline (batch, chạy theo lịch) | Online (theo request) |
|---|---|
| Thu thập bài mới (hằng ngày) | Dựng / cập nhật hồ sơ khi có phản hồi |
| Tính embedding bài mới | Sinh ứng viên từ index |
| Lọc reference, tính trọng số cạnh | Xếp hạng, re-ranking |
| Tính coupling / co-citation top-k (hằng tuần) | Sinh giải thích |
| Tính điểm chất lượng | Ghi log |
| Dựng lại FAISS index | |
| Sinh digest (hằng tuần) | |

---

## 5. Khối 1: Thu thập và làm sạch reference

### 5.1 Mục tiêu

Mỗi cạnh trích dẫn p → r được gán trọng số w(p, r) ∈ [0, 1] phản ánh mức độ **thực sự liên quan**, thay vì coi mọi reference như nhau (giải quyết V3).

### 5.2 Đặc trưng cho mỗi cạnh

| Đặc trưng | Ý nghĩa | Nguồn |
|---|---|---|
| `is_influential` | Semantic Scholar đánh giá cạnh này có ảnh hưởng lớn | S2 |
| `intent ∈ {methodology, result}` | trích để dùng phương pháp / so sánh kết quả, liên quan chặt hơn `background` | S2 |
| `mention_count` | số lần nhắc trong toàn văn | GROBID |
| `in_method_or_exp` | có xuất hiện trong phần Method / Experiments | GROBID |
| `only_in_list` | chỉ xuất hiện trong một chuỗi citation dài, ví dụ "[3–12]" | GROBID |
| `content_sim` | cos(e_p, e_r) | SPECTER2 |
| `deg_in(r)` | số bài trong corpus trích r, dùng để phát hiện hub | đồ thị |

### 5.3 Công thức trọng số

**Phiên bản MVP** (chỉ cần S2 + embedding):

```
w(p, r) = 0.5 · content_sim_norm(p, r) + 0.5 · [is_influential]
```

**Phiên bản đầy đủ**:

```
s(p, r) = a·[is_influential]
        + b·[intent ∈ {methodology, result}]
        + c·log(1 + mention_count)
        + d·[in_method_or_exp]
        − e·[only_in_list]
        + f·content_sim(p, r)

w(p, r) = σ(s(p, r)) · idf(r)
idf(r)  = log(N / (1 + deg_in(r))) / log(N)      # chuẩn hoá về [0, 1]
```

- Bỏ cạnh có `w < θ_edge` (mặc định 0,3, chỉnh theo phân phối thực tế).
- Bỏ hẳn hub có `deg_in` thuộc top 0,1%, hoặc chỉ để IDF xử lý.

**Cách chọn hệ số a…f**:
1. Đặt tay ban đầu (a = 1,5; b = 1; c = 0,5; d = 0,5; e = 0,5; f = 2).
2. Nâng cao: gán nhãn tay khoảng 200–300 cạnh ("liên quan" / "không liên quan"), huấn luyện logistic regression. Dùng nhãn này để báo cáo precision / recall của bộ lọc.

### 5.4 Đầu ra

Bảng `citations` với cột `weight`. Ma trận thưa **A** (n_papers × n_refs) chứa w(p, r), dùng cho Khối 2.

---

## 6. Khối 2: Biểu diễn bài báo

### 6.1 Embedding nội dung

- Mô hình: **SPECTER2** (`allenai/specter2_base` + adapter `proximity`), đầu vào `title [SEP] abstract`.
- Lấy sẵn từ Semantic Scholar nếu có; nếu không thì tự chạy (GPU trên Colab là đủ cho vài chục nghìn bài).
- Chuẩn hoá L2 để cosine = tích vô hướng.
- Lưu vào `papers.embedding` và FAISS index (`IndexFlatIP` nếu < 200k bài, `IndexHNSWFlat` nếu lớn hơn).

### 6.2 Láng giềng cấu trúc

Với **A** đã lọc và trọng số hoá:

- **Bibliographic coupling**: B = Â · Âᵀ, với Â là A chuẩn hoá L2 theo hàng → cosine coupling.
- **Co-citation**: C = Âᵀ · Â (trên cột, sau khi chuẩn hoá theo cột).

**Độ phức tạp**:
- Ngây thơ: O(n² · k̄).
- Nhân ma trận thưa: coupling tốn Σᵣ deg_in(r)², co-citation tốn Σₚ deg_out(p)².
- Hub chi phối chi phí, nên **lọc hub trước khi nhân** vừa giảm chi phí vừa tăng chất lượng.

**Triển khai**:

```python
import numpy as np, scipy.sparse as sp
from sklearn.preprocessing import normalize

def coupling_topk(A: sp.csr_matrix, k=50, hub_pct=99.9):
    deg_in = np.asarray((A > 0).sum(axis=0)).ravel()
    keep = deg_in <= np.percentile(deg_in, hub_pct)
    idf = np.log(A.shape[0] / np.maximum(deg_in, 1)) * keep
    W = normalize(A @ sp.diags(idf), norm="l2", axis=1)
    B = (W @ W.T).tocsr()
    B.setdiag(0); B.eliminate_zeros()
    result = {}
    for i in range(B.shape[0]):
        s, e = B.indptr[i], B.indptr[i + 1]
        if s == e:
            continue
        idx = np.argsort(-B.data[s:e])[:k]
        result[i] = list(zip(B.indices[s:e][idx], B.data[s:e][idx]))
    return result
```

- Nếu hết RAM: dùng `sparse_dot_topn` (nhân và cắt top-k cùng lúc).
- **Cập nhật online cho bài mới**: dùng inverted index `ref → [các bài trích ref]`. Với bài mới p, duyệt mọi r ∈ refs(p), cộng dồn điểm cho các bài cùng trích r. Chi phí Σ_{r ∈ p} deg_in(r).
- **Lưu ý cold-start**: bài mới có coupling ngay (chỉ cần reference của chính nó) nhưng chưa có co-citation. Coupling dùng cho digest bài mới; co-citation dùng cho chế độ "Nền tảng".

### 6.3 Điểm chất lượng q_p

**Bài có review (OpenReview)**:

```
rating_z      = (rating − μ_venue,year) / σ_venue,year         # chuẩn hoá theo venue-năm
r̄_p          = trung bình rating_z có trọng số confidence
q_review(p)   = (n_p · r̄_p + m · μ₀) / (n_p + m)               # Bayesian average, m = 3, μ₀ = 0
bonus_dec(p)  = {oral: 1.0, spotlight: 0.7, poster: 0.4, reject: 0, withdrawn: −0.2, unknown: 0.2}
bonus_code(p) = 0.1 nếu có link code
```

**Bài cũ hoặc không có review**:

```
velocity(p) = citation_count / max(tháng_kể_từ_đăng, 3)
q_cite(p)   = percentile của velocity trong cùng năm và cùng lĩnh vực
```

**Kết hợp**:

```
q(p) = 0.5 · sigmoid(q_review) + 0.3 · bonus_dec + 0.1 · bonus_code + 0.1 · q_cite
```

Nếu thiếu thành phần nào thì chuẩn hoá lại trọng số trên các thành phần còn lại. Đưa q về [0, 1].

**Lưu ý**: không dùng h-index tác giả làm tín hiệu chính (thiên vị tác giả nổi tiếng). Ghi rõ popularity bias trong báo cáo.

### 6.4 (Nâng cao) Graph embedding

Node2vec hoặc LightGCN trên đồ thị citation đã lọc cộng đồ thị đồng tác giả. Ghép với embedding nội dung: e'_p = [e_p ; g_p], hoặc dùng làm đặc trưng riêng cho ranking.

---

## 7. Khối 3: Hồ sơ người dùng ("mình là ai")

### 7.1 Xác định danh tính

| Cách | Mô tả | Ghi chú |
|---|---|---|
| Liên kết OpenReview profile | nhập ID `~Ten_Ho1` hoặc đăng nhập OpenReview | ID duy nhất, không nhầm người trùng tên. **Dùng cho MVP** |
| Liên kết Semantic Scholar / ORCID | nhập author ID | phủ thêm bài ngoài OpenReview |
| Khai báo tên | tìm tác giả trùng tên, phân giải bằng tên + đồng tác giả + chủ đề | bắt buộc có bước người dùng xác nhận |

Sau khi liên kết: hiển thị màn **"Đây có phải bài của bạn?"** để người dùng tick / bỏ tick (`user_papers.confirmed`).

### 7.2 Các tập bài và trọng số

| Role | Nguồn | Trọng số cơ sở β_role |
|---|---|---|
| `authored` | bài có `authorids` chứa ID người dùng | 1.0 (× 1.2 nếu là tác giả đầu) |
| `cited` | reference của các bài `authored`, **đã lọc** | 0.5 × w(p, r) |
| `saved` | lưu trong app / import | 0.7 |
| `read` | đánh dấu đã đọc, import BibTeX / Zotero | 0.3 |

**Time decay**:

```
weight(u, p) = β_role · exp(−Δt_năm / τ),   τ = 3 năm
```

Gộp nếu một bài có nhiều role: lấy max.

### 7.3 Đa sở thích

1. Lấy tập bài P_u cùng embedding và trọng số.
2. Phân cụm **có trọng số**: k-means với k = min(5, ⌈|P_u| / 5⌉), hoặc HDBSCAN để tự xác định số cụm.
3. Mỗi cụm c: centroid u_c = Σ weight · e_p / ‖·‖, trọng số cụm π_c = tổng weight trong cụm (chuẩn hoá).
4. Nhãn cụm: top keywords (TF-IDF trên title + keywords các bài trong cụm). Người dùng đổi tên được.
5. Người dùng có thể **tắt** cụm (`muted`) hoặc **tăng / giảm** π_c.

### 7.4 Cold-start phân tầng

| Tầng | Điều kiện | Cách dựng hồ sơ |
|---|---|---|
| 1 | Có bài đã publish | tự động từ `authored` + `cited` |
| 2 | Chưa publish, có thư viện đọc | import BibTeX / Zotero → `read` / `saved` |
| 3 | Hoàn toàn mới | chọn chủ đề (seed papers đại diện mỗi chủ đề) hoặc dán abstract đề tài → embedding làm 1 cụm |

### 7.5 Tín hiệu bổ sung từ danh tính

- **Mạng đồng tác giả**: tập CoA₁ (đồng tác giả trực tiếp), CoA₂ (bậc 2).
- **Bài trích bài của mình**: tập CitesMe = {p : ∃ r ∈ authored(u), (p → r) ∈ citations, w ≥ θ}.
- **Venue quen thuộc**: phân phối venue của bài `authored`.

---

## 8. Khối 4: Sinh ứng viên

Mục tiêu: khoảng 300–500 ứng viên mỗi người dùng mỗi lần chạy. Nhiều nguồn song song, gộp và khử trùng lặp, lưu lại nguồn của từng ứng viên (`sources`).

### 8.1 Pool theo chế độ

| Chế độ | Pool bài được phép | Mục đích |
|---|---|---|
| **Digest / Mới** | `pub_date ≥ now − N ngày` (N = 7 cho digest tuần, 30 cho feed) | V1: bài cũ không bao giờ cạnh tranh với bài mới |
| **Nền tảng** | mọi bài, ưu tiên bài có co-citation cao | đọc nền cho chủ đề |
| **Khám phá** | mọi bài, ứng viên xa hồ sơ hơn | serendipity |
| **Tương tự bài X** | mọi bài | item-to-item |

### 8.2 Các nguồn ứng viên

| Nguồn | Thuật toán | Số lượng | Dùng ở chế độ |
|---|---|---|---|
| `content` | với mỗi cụm c: FAISS top-K theo u_c (K tỉ lệ π_c), lọc theo pool | 200 | tất cả |
| `coupling` | láng giềng coupling của các bài trong P_u (top theo weight) | 100 | Mới, Tương tự |
| `cocitation` | láng giềng co-citation của P_u | 100 | Nền tảng, Tương tự |
| `graph_expand` | bài được trích bởi / trích P_u, cạnh đã lọc | 50 | Nền tảng, Khám phá |
| `cites_me` | CitesMe | tất cả | Mới |
| `coauthor` | bài mới của CoA₁ ∪ CoA₂ | 50 | Mới |

Với FAISS và pool theo thời gian: hoặc tạo **index riêng cho bài mới** (rebuild hằng ngày, nhỏ và nhanh), hoặc tìm top lớn rồi lọc theo `pub_date`. Khuyến nghị cách 1.

### 8.3 Loại bỏ cứng (trước khi ranking)

- Bài `authored` của người dùng.
- Bài người dùng đã `cited`, `read`, `saved`.
- Bài có phản hồi `not_relevant` hoặc `already_read`.
- Bài đã gợi ý ở digest trước mà người dùng không tương tác (tránh lặp; tuỳ chọn cho phép lặp tối đa 1 lần).

---

## 9. Khối 5: Xếp hạng

### 9.1 Đặc trưng cho mỗi cặp (u, p)

| Nhóm | Đặc trưng |
|---|---|
| Liên quan | `rel_max = max_c π'_c · cos(u_c, e_p)`; `rel_top_cluster`; cos với bài gần nhất trong P_u |
| Đồ thị | điểm coupling max / tổng với P_u; điểm co-citation; số cạnh đã lọc nối p với P_u |
| Chất lượng | q(p); decision; số review; `has_code` |
| Thời gian | `fresh = exp(−tuổi_ngày / τ_f)`; tuổi theo tháng |
| Danh tính | `is_cites_me`; `is_coauthor_1`; `is_coauthor_2`; venue có trong venue quen thuộc |
| Nguồn | one-hot `sources`; số nguồn cùng đề xuất p |

π'_c là trọng số cụm đã chuẩn hoá về [0,5; 1] để cụm nhỏ không bị bỏ qua hoàn toàn.

### 9.2 MVP: hàm tuyến tính

```
score(u, p) = α · rel_max + β · q(p) + γ · fresh + δ · graph + ε · identity

graph    = 0.6 · coupling_norm + 0.4 · cocitation_norm
identity = 0.5 · is_cites_me + 0.3 · is_coauthor_1 + 0.2 · is_coauthor_2
```

Trọng số mặc định theo chế độ:

| Chế độ | α | β | γ | δ | ε |
|---|---|---|---|---|---|
| Digest / Mới | 0.50 | 0.20 | 0.10 | 0.10 | 0.10 |
| Nền tảng | 0.45 | 0.30 | 0.00 | 0.25 | 0.00 |
| Khám phá | 0.30 | 0.40 | 0.10 | 0.20 | 0.00 |

Ghi chú: trong chế độ Digest, độ mới đã được đảm bảo bằng pool nên γ chỉ để phân biệt trong tuần. Chỉnh trọng số bằng grid search trên tập validation (Mục 12).

### 9.3 Nâng cao: Learning-to-Rank

- Mô hình: **LightGBM `LGBMRanker`**, objective `lambdarank`, metric `ndcg@10`.
- Mỗi query = một người dùng (tác giả) tại thời điểm T; ứng viên lấy từ Khối 4; nhãn từ giao thức Mục 12.1 (1 nếu tác giả trích p sau T với cạnh đã lọc, ngược lại 0).
- Chia train / val / test theo **thời gian** và theo **người dùng**.
- Dùng feature importance / SHAP để sinh giải thích và để báo cáo.

---

## 10. Khối 6: Xếp hạng lại, lọc và giải thích

### 10.1 Đa dạng hoá bằng MMR

Chọn lần lượt từ danh sách đã xếp hạng R vào danh sách kết quả S:

```
p* = argmax_{p ∈ R \ S} [ λ · score(p) − (1 − λ) · max_{s ∈ S} cos(e_p, e_s) ]
```

λ = 0.7 mặc định; người dùng chỉnh bằng thanh trượt "Sát chủ đề ↔ Đa dạng".

### 10.2 Hạn mức theo cụm sở thích

Danh sách L mục được chia suất cho các cụm theo π_c, mỗi cụm không bị tắt có ít nhất 1 suất. Trong digest, các bài được nhóm hiển thị theo cụm.

### 10.3 Suất khám phá

1–2 suất cho bài có `q(p)` cao và `rel_max` ở mức trung bình (ví dụ trong khoảng phân vị 50–80 của ứng viên). Gắn nhãn "Khám phá" trên giao diện.

### 10.4 Sinh lời giải thích

Chọn đặc trưng đóng góp nhiều nhất (với hàm tuyến tính: thành phần lớn nhất của score; với LightGBM: SHAP), ánh xạ sang mẫu câu:

| Đặc trưng chính | Mẫu giải thích |
|---|---|
| `rel_max` | "Gần với bài *{X}* bạn đã viết / lưu" (X = bài trong P_u gần nhất) |
| coupling | "Chung {k} tài liệu tham khảo quan trọng với *{X}*" |
| cocitation | "Thường được trích cùng *{X}*" |
| `is_cites_me` | "Trích bài *{X}* của bạn" |
| coauthor | "Của {tên}, đồng tác giả của bạn" |
| quality | "Oral ICLR 2026, điểm review cao" |

Mỗi gợi ý hiển thị tối đa 2 lý do. Toàn bộ `score_parts` lưu trong `recommendation_log`.

---

## 11. Khối 7: Vòng phản hồi

| Hành động | Tác động |
|---|---|
| `saved` | thêm vào P_u với role `saved` |
| `relevant` | Rocchio: u_c ← normalize(u_c + η₊ · e_p), η₊ = 0.1, với c là cụm gần p nhất |
| `not_relevant` | u_c ← normalize(u_c − η₋ · e_p), η₋ = 0.05; loại p khỏi gợi ý sau |
| `already_read` | thêm vào P_u với role `read`; loại p |
| `less_like_this` (theo chủ đề / venue) | giảm π_c của cụm tương ứng hoặc thêm bộ lọc venue |
| `clicked` (không lưu) | chỉ ghi log, làm implicit feedback cho LTR sau này |

Định kỳ (hằng tuần) **phân cụm lại** toàn bộ P_u để tránh trôi centroid.

---

## 12. Đánh giá

### 12.1 Giao thức "tác giả là người dùng"

Dùng **chính pipeline của sản phẩm** để đánh giá offline.

1. Chọn tác giả có ≥ 3 bài trong corpus, trong đó ≥ 1 bài đăng sau thời điểm T.
2. **Hồ sơ tại T**: chỉ dùng các bài `authored` và `cited` có thời gian < T. Mọi thống kê (coupling, co-citation, citation_count, điểm chất lượng dựa trên citation) **phải tính lại chỉ với dữ liệu < T** để tránh rò rỉ.
3. **Ground truth**: các bài trong corpus được tác giả trích ở các bài đăng **sau T**, chỉ tính cạnh có w ≥ θ_edge, và loại những bài tác giả đã trích trước T.
4. Với chế độ Digest: ground truth chỉ gồm bài đăng trong khoảng [T, T + Δ].
5. Chia theo thời gian: T_train < T_val < T_test. Chia tác giả thành tập train / val / test riêng cho LTR.

### 12.2 Độ đo

| Nhóm | Độ đo | Gắn với |
|---|---|---|
| Độ chính xác | Recall@k, NDCG@k, MRR (k = 10, 20) | chung |
| Tính mới | tuổi trung bình bài gợi ý; tỉ lệ bài < 30 ngày | V1 |
| Chất lượng | q trung bình của danh sách; tỉ lệ bài accept | V2 |
| Đa dạng | khoảng cách trung bình giữa các cặp trong danh sách (intra-list distance) | |
| Coverage | tỉ lệ corpus từng xuất hiện trong ít nhất một danh sách | popularity bias |
| Bộ lọc reference | precision / recall trên tập cạnh gán nhãn tay | V3 |

### 12.3 Baseline và ablation

| # | Cấu hình |
|---|---|
| B0 | Random (trong pool) |
| B1 | Popularity: nhiều citation nhất |
| B2 | Chỉ content, hồ sơ là 1 vector trung bình |
| B3 | Content + hồ sơ đa sở thích |
| B4 | B3 + đồ thị với reference **chưa lọc** |
| B5 | B3 + đồ thị với reference **đã lọc** |
| B6 | B5 + chất lượng |
| B7 | B6 + re-ranking (MMR, hạn mức) |
| B8 | B7 với LightGBM LambdaRank thay hàm tuyến tính |

So sánh **B4 và B5** trả lời trực tiếp câu hỏi về reference nhiễu. Báo cáo cả đánh đổi: đa dạng tăng thì NDCG có thể giảm nhẹ.

### 12.4 (Tuỳ chọn) Đánh giá với người thật

5–10 người (thầy cô, anh chị cao học) liên kết OpenReview ID, chấm 20 gợi ý mỗi người trên thang 1–5 về độ liên quan, độ mới, độ hữu ích.

---

## 13. Tính năng phần mềm

Ký hiệu: 🟢 bắt buộc (MVP) · 🟡 nên có · ⚪ nếu còn thời gian

### 13.1 Onboarding và hồ sơ

| Tính năng | Ưu tiên | Liên quan |
|---|---|---|
| Liên kết OpenReview ID / đăng nhập OpenReview | 🟢 | 7.1 |
| Màn "Đây có phải bài của bạn?" | 🟢 | 7.1 |
| Chọn chủ đề / dán abstract đề tài (cold-start tầng 3) | 🟢 | 7.4 |
| Import BibTeX / Zotero | 🟡 | 7.4 |
| Xem và chỉnh cụm sở thích (đổi tên, tắt, tăng/giảm) | 🟡 | 7.3 |

### 13.2 Trang chủ: digest và feed

| Tính năng | Ưu tiên | Liên quan |
|---|---|---|
| Digest hằng tuần chỉ gồm bài mới, nhóm theo cụm | 🟢 | V1, 8.1 |
| Badge chất lượng: decision, điểm review chuẩn hoá, có code | 🟢 | V2, 6.3 |
| "Vì sao gợi ý bài này" | 🟢 | 10.4 |
| Mục "Bài mới trích bài của bạn" | 🟡 | 7.5 |
| Mục "Từ đồng tác giả và mạng lưới" (có thể tắt) | 🟡 | 7.5 |
| Cài đặt tần suất và gửi email | ⚪ | |

### 13.3 Trang chi tiết bài báo

| Tính năng | Ưu tiên | Liên quan |
|---|---|---|
| Abstract, TL;DR, link PDF / OpenReview / code | 🟢 | |
| Tóm tắt review: điểm, decision, meta-review | 🟡 | V2 |
| Bài tương tự, chia tab: nội dung / chung reference / hay được trích cùng | 🟢 | 6.1, 6.2 |
| Reference đã phân loại: "cốt lõi" và "nền / background" | 🟡 | V3, 5.3 |
| Danh sách bài trích bài này | ⚪ | |

### 13.4 Khám phá và tìm kiếm

| Tính năng | Ưu tiên | Liên quan |
|---|---|---|
| Ba chế độ: Mới / Nền tảng / Khám phá | 🟡 | 8.1 |
| Tìm kiếm ngữ nghĩa | 🟡 | 6.1 |
| Bộ lọc: venue, năm, decision, có code | 🟢 | |
| Thanh trượt Mới ↔ Kinh điển, Sát chủ đề ↔ Đa dạng | ⚪ | γ, λ |

### 13.5 Phản hồi và thư viện

| Tính năng | Ưu tiên | Liên quan |
|---|---|---|
| Nút Liên quan / Không liên quan / Đã đọc | 🟢 | 11 |
| "Ít bài như thế này hơn" | 🟡 | 11 |
| Lưu vào thư viện, thư mục, trạng thái đọc | 🟡 | 7.2 |
| Xuất BibTeX | ⚪ | |

### 13.6 Trợ lý viết

| Tính năng | Ưu tiên | Liên quan |
|---|---|---|
| Dán bản nháp → gợi ý bài liên quan chưa trích | ⚪ | dùng bản nháp làm hồ sơ 1 cụm |

### 13.7 Chế độ demo / debug

| Tính năng | Ưu tiên | Liên quan |
|---|---|---|
| Phân rã điểm từng gợi ý (rel, quality, fresh, graph, identity) | 🟢 | 9.2 |
| Bật / tắt từng thành phần và xem danh sách thay đổi | 🟡 | 12.3 |
| "Du hành thời gian": hồ sơ tác giả tại T, so với bài họ trích thật sau T | ⚪ | 12.1 |

---

## 14. Kiến trúc hệ thống và công nghệ

```
┌───────────────┐      ┌──────────────────────────┐      ┌─────────────────┐
│  Frontend     │ HTTP │  Backend API (FastAPI)   │      │  PostgreSQL     │
│  Next.js /    │─────►│  - recommend service     │─────►│  + pgvector     │
│  Streamlit    │      │  - profile service       │      └─────────────────┘
└───────────────┘      │  - feedback service      │      ┌─────────────────┐
                       │                          │─────►│  FAISS index    │
                       └────────────▲─────────────┘      │  (all + recent) │
                                    │                    └─────────────────┘
                       ┌────────────┴─────────────┐      ┌─────────────────┐
                       │  Batch jobs (APScheduler │─────►│  GROBID (Docker)│
                       │  / cron)                 │      └─────────────────┘
                       │  - crawl OpenReview      │
                       │  - fetch S2 references   │──► OpenReview API, Semantic Scholar API
                       │  - embed, filter, graph  │
                       │  - quality, digest       │
                       └──────────────────────────┘
```

| Thành phần | Đề xuất | Ghi chú |
|---|---|---|
| Ngôn ngữ | Python 3.11 | |
| Thu thập | `openreview-py`, `requests` + backoff | |
| Parse PDF | GROBID (Docker) | chỉ khi S2 thiếu |
| Embedding | `transformers` + `adapters` (SPECTER2) | chạy trên Colab nếu không có GPU |
| Vector search | FAISS | hoặc pgvector nếu corpus nhỏ |
| Đồ thị | `scipy.sparse`, `sparse_dot_topn` | node2vec: `torch_geometric` (nâng cao) |
| Phân cụm | `scikit-learn` (KMeans), `hdbscan` | |
| Ranking | hàm tuyến tính → `lightgbm` | |
| Backend | FastAPI | |
| DB | PostgreSQL + pgvector | |
| Lịch chạy | APScheduler hoặc cron | |
| Frontend | Streamlit (nhanh cho demo) hoặc Next.js | |
| Đánh giá | `ranx` hoặc tự viết metric | |

### Cấu trúc thư mục gợi ý

```
paper-recsys/
├── data/                   # cache thô, không commit
├── ingest/
│   ├── openreview_crawler.py
│   ├── s2_client.py
│   └── grobid_parser.py
├── features/
│   ├── embeddings.py
│   ├── reference_filter.py
│   ├── graph.py            # coupling, co-citation
│   └── quality.py
├── recsys/
│   ├── profile.py          # hồ sơ, phân cụm, cold-start
│   ├── candidates.py
│   ├── ranking.py
│   ├── rerank.py           # MMR, hạn mức, khám phá
│   └── explain.py
├── eval/
│   ├── protocol.py         # author-as-user, cắt thời gian
│   ├── metrics.py
│   └── run_ablation.py
├── api/
│   └── main.py             # FastAPI
├── jobs/
│   └── scheduler.py
├── app/                    # frontend
└── notebooks/
```

---

## 15. API backend

| Method | Endpoint | Mô tả |
|---|---|---|
| POST | `/users` | tạo người dùng |
| POST | `/users/{id}/identity` | liên kết OpenReview / S2 ID |
| GET | `/users/{id}/candidate-papers` | danh sách bài nghi là của người dùng để xác nhận |
| POST | `/users/{id}/papers/confirm` | xác nhận / bỏ xác nhận bài |
| POST | `/users/{id}/import` | import BibTeX |
| GET | `/users/{id}/profile` | các cụm sở thích |
| PATCH | `/users/{id}/clusters/{cid}` | đổi tên, tắt, chỉnh trọng số cụm |
| GET | `/recommend?user_id=&mode=digest\|new\|foundational\|explore&k=` | danh sách gợi ý kèm giải thích và `score_parts` |
| GET | `/papers/{pid}` | chi tiết bài |
| GET | `/papers/{pid}/similar?kind=content\|coupling\|cocitation` | bài tương tự |
| GET | `/papers/{pid}/references` | reference đã phân loại cốt lõi / nền |
| GET | `/search?q=&filters=` | tìm kiếm ngữ nghĩa |
| POST | `/feedback` | ghi phản hồi |
| POST | `/assist/related-work` | dán bản nháp, trả về bài chưa trích |
| GET | `/debug/recommend?user_id=&as_of=&disable=` | chế độ demo: du hành thời gian, tắt thành phần |

---

## 16. Lộ trình và phân công

| Giai đoạn | Thời gian | Nội dung | Kết quả |
|---|---|---|---|
| 1 | Tuần 1–2 | Thu thập OpenReview + S2; DB; embedding SPECTER2; FAISS; gợi ý content-based | B2 chạy được; dữ liệu sạch |
| 2 | Tuần 3–4 | Lọc reference; coupling / co-citation; điểm chất lượng; ranking tuyến tính; giao thức đánh giá | B4–B6, bảng kết quả đầu tiên |
| 3 | Tuần 5–6 | Hồ sơ "mình là ai", đa sở thích, cold-start; MMR, hạn mức; giải thích; giao diện; chế độ debug | MVP đầy đủ, B7 |
| 4 | Tuần 7+ | LightGBM LambdaRank; graph embedding; đánh giá với người thật; báo cáo | B8, báo cáo cuối |

Phân công gợi ý cho nhóm 4 người:

| Thành viên | Phụ trách |
|---|---|
| A | Thu thập dữ liệu, DB, batch jobs |
| B | Embedding, lọc reference, đồ thị, chất lượng |
| C | Hồ sơ người dùng, sinh ứng viên, ranking, re-ranking |
| D | Đánh giá (giao thức, metric, ablation), frontend, demo |

---

## 17. Rủi ro và lưu ý

| Rủi ro | Giảm thiểu |
|---|---|
| Schema OpenReview khác nhau giữa venue / năm | parser theo từng venue; kiểm thử với note mẫu |
| Bị giới hạn request | nghỉ giữa request, backoff, cache, ưu tiên S2 cho reference |
| S2 không tra được nhiều bài | tra theo nhiều khoá (arXiv ID, DOI, title); GROBID dự phòng |
| **Rò rỉ dữ liệu theo thời gian** khi đánh giá | mọi thống kê tính lại với dữ liệu < T; viết test riêng cho protocol |
| Popularity bias từ điểm chất lượng | đo coverage; giới hạn β; ghi rõ trong báo cáo |
| Trùng tên tác giả | dùng OpenReview ID; bắt buộc bước xác nhận |
| Danh tính bị "nhận vơ" | dữ liệu công khai nên rủi ro thấp; nếu cần, yêu cầu đăng nhập OpenReview |
| Corpus nhỏ, chỉ ML | khoanh rõ phạm vi; có thể mở rộng bằng arXiv |
| Điểm review nhiễu, thang khác nhau | chuẩn hoá z-score theo venue-năm, Bayesian average, trọng số confidence |

---

## 18. Phụ lục: tham số mặc định

| Tham số | Giá trị | Mục |
|---|---|---|
| θ_edge (ngưỡng cạnh) | 0.3 | 5.3 |
| Ngưỡng hub | top 0.1% deg_in | 5.3, 6.2 |
| k láng giềng lưu sẵn | 50 | 6.2 |
| m (Bayesian average) | 3 | 6.3 |
| τ (decay hồ sơ) | 3 năm | 7.2 |
| Số cụm tối đa | 5 | 7.3 |
| N ngày (digest / feed) | 7 / 30 | 8.1 |
| τ_f (decay độ mới khi xếp hạng) | 14 ngày | 9.1 |
| λ (MMR) | 0.7 | 10.1 |
| Số suất khám phá | 1–2 / 10 | 10.3 |
| η₊ / η₋ (Rocchio) | 0.1 / 0.05 | 11 |
| k khi đánh giá | 10, 20 | 12.2 |

Các giá trị trên là điểm khởi đầu; chỉnh bằng grid search trên tập validation và ghi lại trong báo cáo.
