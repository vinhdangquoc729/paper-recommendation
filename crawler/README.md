# Module 1: crawler

Thu thập dữ liệu thô, lưu cache, rồi chuẩn hoá vào SQLite.

```
API ──► data/raw/ (cache thô, JSONL) ──► python -m crawler load ──► data/corpus.sqlite
```

Tách "cào" và "load" để: (1) không bao giờ phải cào lại khi sửa parser; (2) chạy lại bước nào cũng được.

## Nguồn

| Lệnh | Nguồn | Lấy gì | Cache |
|---|---|---|---|
| `s2-papers` | S2 `/paper/search/bulk` theo venue | metadata bài đã accept: title, abstract, tác giả, ngày, citation | `raw/s2/papers_{venue}.jsonl` |
| `s2-refs` | S2 `/paper/batch` | danh sách reference (paperId, năm) | `raw/s2/references.jsonl` (resume) |
| `s2-edges --sample N` | S2 `/paper/{id}/references` | `intents`, `isInfluential`, `contexts` cho N bài | `raw/s2/edges_sample.jsonl` (resume) |
| `openreview` | OpenReview API v1/v2 (cần đăng nhập) | submission kể cả reject, review, decision | `raw/openreview/{venue}_{edition}.jsonl.gz` |

Venue và edition khai báo ở [venues.py](venues.py).

## Biến môi trường (`.env`)

- `S2_API_KEY`: không bắt buộc, nhưng thiếu key thì pool ẩn danh hay bị 429 và rất chậm.
  Xin key miễn phí tại https://www.semanticscholar.org/product/api#api-key-form
- `OPENREVIEW_USERNAME`, `OPENREVIEW_PASSWORD`: bắt buộc cho lệnh `openreview`
  (OpenReview đang chặn request ẩn danh bằng `ChallengeRequiredError`).

## Hợp đồng dữ liệu đầu ra

Xem [schema.sql](schema.sql). Khoá chính của bài là S2 `paperId`; bài OpenReview nối sang qua
`or_submissions.s2_paper_id` (khớp tiêu đề chuẩn hoá trong cùng venue).

## Những điều đã biết về dữ liệu

- S2 **ẩn reference** của nhiều bài theo yêu cầu nhà xuất bản (`refs_status = 'elided'`): 58% corpus,
  bài càng mới càng nặng (NeurIPS 2025: 92%, ICLR 2025: 62%). Endpoint `/references` (intents, contexts)
  cũng bị ẩn với các bài này.
- OpenAlex **không bù được**: 0/40 bài bị ẩn trên S2 có reference trên OpenAlex (bản arXiv và proceedings
  NeurIPS không gửi reference lên Crossref). Muốn có reference cho phần còn lại phải parse PDF (GROBID).
- Năm trên S2 thường là năm lên arXiv; năm hội nghị lấy từ DBLP key (`conf/iclr/...24`).
- S2 gắn venue cho ICLR 2026 chưa đầy đủ (mới thấy 19 bài): cần OpenReview làm nguồn chính cho năm này.
- API OpenReview: ICLR 2023 ở v1 (content không bọc `{"value": ...}`), các venue còn lại ở v2;
  `rating` là chuỗi kiểu `"6: marginally above..."`; bài đang review có `authorids` bị ẩn.
- Độ phủ OpenReview (cào 10/2026, 78.666 submission):
  - ICLR: đủ cả accept / reject / withdrawn, ~98% có review và rating.
  - NeurIPS: ~95% là bài accept (chỉ công khai bài accept + bài reject tự nguyện công khai), có review.
  - ICML: chỉ bài accept; 2023–2024 không có review, 2025+ có (`overall_recommendation`).
  - TMLR: có review nhưng **không có điểm số** (thiết kế của TMLR); bài reject giữ ẩn danh.
- Submission dồn cục theo đợt: 64,5% số bài rơi vào 5 tuần (ngày mở submission của ICLR/ICML).
