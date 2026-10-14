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
| `eval-refs --t T --authors N` | arXiv e-print (source LaTeX) | reference cho bài sau T của N tác giả lấy mẫu: danh sách reference (.bbl, hoặc .bib nếu không có .bbl) và từng lần trích dẫn trong .tex | `raw/eval/targets_*.jsonl`, `raw/arxiv/title_lookup.jsonl`, `raw/arxiv/bbl.jsonl.gz` |

Venue và edition khai báo ở [venues.py](venues.py).

## Biến môi trường (`.env`)

- `S2_API_KEY`: không bắt buộc, nhưng thiếu key thì pool ẩn danh hay bị 429 và rất chậm.
  Xin key miễn phí tại https://www.semanticscholar.org/product/api#api-key-form
- `OPENREVIEW_USERNAME`, `OPENREVIEW_PASSWORD`: bắt buộc cho lệnh `openreview`
  (OpenReview đang chặn request ẩn danh bằng `ChallengeRequiredError`).

## Dữ liệu đầu ra

Xem [schema.sql](schema.sql). Khoá chính của bài là S2 `paperId`; bài OpenReview nối sang qua
`or_submissions.s2_paper_id` (khớp tiêu đề chuẩn hoá trong cùng venue).

## Reference từ source LaTeX (cho V3 và cho đánh giá)

OpenReview không có reference. Lệnh `eval-refs` lấy reference từ source LaTeX trên arXiv:

1. Chọn mẫu tác giả đủ điều kiện ở mốc T (>= 2 bài trước T, >= 1 bài sau T) và các bài sau T của họ
   ([eval_targets.py](eval_targets.py)).
2. Tìm arXiv ID theo tiêu đề: S2 `/paper/search/match` rồi API arXiv, chấp nhận khi tiêu đề giống >= 95%
   ([arxiv_ids.py](arxiv_ids.py)).
3. Tải gói e-print, lấy danh sách reference từ .bbl (hoặc các mục .bib được trích nếu bài chỉ nộp .bib),
   và đọc các lệnh cite trong .tex: khoá, section, có trong phụ lục không, đoạn văn quanh nó ([latex.py](latex.py)).
4. `load` dựng `or_refs`: mỗi reference ghép về bài OpenReview (theo arXiv ID, rồi tiêu đề) kèm đặc trưng
   trích dẫn của spec mục 5.2: `n_mentions`, `n_sections`, `in_intro/related/method/experiment`,
   `appendix_only`, `only_in_list` (chỉ nằm trong cite có >= 4 khoá).

Crawler không dừng vì lỗi hay giới hạn: 429/503 thì chờ theo Retry-After, lỗi tạm thời được ghi lại và thử lại
(tối đa 3 vòng mỗi lần chạy, chạy lại lệnh thì tiếp tục từ chỗ dở).

Hạn chế: chỉ bài có trên arXiv mới có reference (khoảng 2/3 số bài sau T); section đặt tên tự do
("Do We Need Adam?") không phân loại được nên `in_method` / `in_experiment` có thể thiếu.
