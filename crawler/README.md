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
| `eval-refs --t T --authors N` | arXiv HTML, không có thì source LaTeX | reference cho bài sau T của N tác giả lấy mẫu: danh sách reference (.bbl, hoặc .bib nếu không có .bbl) và từng lần trích dẫn trong .tex | `raw/eval/targets_*.jsonl`, `raw/arxiv/title_lookup.jsonl`, `raw/arxiv/bbl.jsonl.gz` |
| `arxiv-oai` | arXiv OAI-PMH (`ListRecords`, set cs, theo tháng cập nhật) | metadata arXiv (id, tiêu đề, họ tác giả, category) từ 2022, khoảng 684.000 bài, 7 phút; ghép tiêu đề (trùng hoặc giống >= 95%) + ít nhất một họ tác giả trùng để có arXiv ID cho bài S2 không gắn (reject, rút, 2026) | `raw/arxiv/oai/cs_YYYY-MM.jsonl`, ghi vào `raw/arxiv/title_lookup.jsonl` |
| `corpus-refs` | arXiv HTML, không có thì source LaTeX | như trên, cho mọi bài trong corpus đã có arXiv ID (khoảng 23.300, chủ yếu bài accept); bài của tập đánh giá tải trước, rồi bài mới trước bài cũ | `raw/arxiv/bbl.jsonl.gz` |

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
   ([arxiv_ids.py](arxiv_ids.py)). Cho cả corpus thì dùng `arxiv-oai` ([arxiv_oai.py](arxiv_oai.py)): tải metadata
   arXiv một lần rồi ghép trên máy. Đối chiếu với arXiv ID S2 đã gắn: tìm lại được 97,9% (22.903 / 23.388), 5 bài lệch
   đều là cùng nhóm tác giả đăng hai bản trùng tên; thêm được 26.262 bài (16.286 bài 2026).
3. Lấy danh sách reference và từng lần trích dẫn (khoá, section, có trong phụ lục không, đoạn văn quanh nó):
   - trước hết từ bản HTML `export.arxiv.org/html/{id}` do LaTeXML sinh ([arxiv_html.py](arxiv_html.py)), nhẹ hơn
     gói source hàng chục lần vì không kèm hình (ví dụ 0,6 MB so với 13,4 MB);
   - không có HTML thì tải gói source `export.arxiv.org/src/{id}`, đọc .bbl (hoặc các mục .bib được trích) và các
     lệnh cite trong .tex ([latex.py](latex.py)); đứt giữa chừng thì tải tiếp bằng header Range.

   So trên 4 bài, hai cách cho kết quả trùng nhau (số reference, số lần trích, trích trong phụ lục, đặc trưng),
   trừ trích dẫn nằm trong hình TikZ (cây phân loại của bài survey) mà LaTeXML không chuyển được: bài survey
   2602.06052 mất 147 / 881 lần trích và 26 / 561 reference.
4. `load` dựng `or_refs`: mỗi reference ghép về bài OpenReview (theo arXiv ID, rồi tiêu đề) kèm đặc trưng
   trích dẫn của spec mục 5.2: `n_mentions`, `n_sections`, `in_intro/related/method/experiment`,
   `appendix_only`, `only_in_list` (chỉ nằm trong cite có >= 4 khoá).

Crawler không dừng vì lỗi hay giới hạn: 429/503 thì chờ theo Retry-After, lỗi tạm thời được ghi lại và thử lại
(tối đa 3 vòng mỗi lần chạy, chạy lại lệnh thì tiếp tục từ chỗ dở).

Chạy song song: mở N terminal, mỗi terminal `python -m crawler corpus-refs --shard I/N` với I = 0..N-1 (cùng N).
Mỗi tiến trình chỉ tải phần bài của mình (chia theo crc32 của arXiv ID) và ghi vào `raw/arxiv/bbl_shard{I}.jsonl.gz`;
`bbl_status` và `load` đọc gộp mọi file. Mỗi file cache có khoá, hai tiến trình không thể ghi cùng một file.
Mỗi tiến trình dùng giãn cách `--src-interval` riêng (mặc định 0,1 giây). Không chạy
lệnh không có `--shard` cùng lúc với các shard: nó tải lại đúng những bài các shard đang tải.

Mỗi bài được ghi nối vào cache ngay khi xong, nên có thể ngắt bất cứ lúc nào (Ctrl+C, cho máy ngủ, kể cả tắt
máy đột ngột) rồi chạy lại đúng lệnh cũ. Nếu lần trước bị giết giữa lúc ghi, lần ghi đầu tiên của lần chạy sau
tự cắt bỏ bản ghi dở ([common/jsonl.py](../common/jsonl.py)).

Thời gian: tải HTML / source giãn cách 0,1 giây (`--src-interval`), 429 thì thử lại ngay (20 lần 429 liên tiếp
thì nghỉ 60 giây). Toàn bộ corpus (khoảng 23.300 bài, 3 shard) mất gần 2 ngày, cache khoảng 260 MB. Giờ cao điểm ở Mỹ arXiv trả
429 "Rate exceeded." ngẫu nhiên cho gần một nửa số request (máy chủ quá tải, không phải bị chặn), nên tốc độ thực tế
phụ thuộc giờ chạy; chạy ban ngày giờ Việt Nam (ban đêm ở Mỹ) nhanh hơn hẳn.
Tra arXiv ID theo tiêu đề chậm hơn nhiều khi không có `S2_API_KEY` (API tìm kiếm của arXiv hay trả 429).

Hạn chế: chỉ bài có trên arXiv mới có reference (khoảng 2/3 số bài sau T); section đặt tên tự do
("Do We Need Adam?") không phân loại được nên `in_method` / `in_experiment` có thể thiếu.
