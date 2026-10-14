# Module 2: features (biểu diễn bài báo)

Khối 2 trong spec. Hiện **chỉ dùng dữ liệu OpenReview**, chưa dùng S2 (reference, citation).

```
data/corpus.sqlite ──► python -m features items | quality | embed ──► data/features/
```

| Lệnh | Làm gì | Đầu ra |
|---|---|---|
| `items` | Mỗi bài một dòng; gộp các lần nộp lại (cùng tiêu đề chuẩn hoá, ≥ 20 ký tự) về bản có kết quả tốt nhất, mới nhất | bảng `items`, `versions` trong `features.sqlite` |
| `quality` | Điểm chất lượng q_p (spec 6.3) | bảng `quality` |
| `embed` | SPECTER2 (`specter2_base` + adapter `proximity`), `title [SEP] abstract`, chuẩn hoá L2 | `specter2.npy`, `specter2_ids.txt` |

## items

- `item_id` = `forum_id` của bản đại diện. `versions` ánh xạ mọi submission về `item_id`.
- `first_seen`: ngày công khai sớm nhất trong các bản (bài reject ở ICLR 2024 rồi accept ở ICML 2024 đã
  công khai từ 10/2023).
- `is_candidate = 1` với accept và reject; withdrawn, desk-reject, đang review chỉ giữ làm dữ liệu.
- Bài đổi tiêu đề khi nộp lại sẽ **không** được gộp.

## quality

```
z            = (rating − μ_venue,năm) / σ_venue,năm        # bỏ venue-năm có < 30 review
rating_z     = trung bình z, trọng số = confidence / confidence trung bình của venue-năm
q_review     = n · rating_z / (n + 3)                       # Bayesian average về 0
bonus_dec    = oral 1 · spotlight 0,7 · poster/accept 0,4 · reject 0 · withdrawn/desk −0,2 · chưa biết 0,2
has_code     = 1/0, chỉ xét ở venue-năm có hỏi link code (ICML 2025+, TMLR), venue khác coi là thiếu
q            = (0,5·sigmoid(q_review) + 0,3·bonus_dec + 0,1·has_code) / tổng trọng số của phần có mặt, cắt về [0, 1]
```

- Review và decision lấy từ **mọi bản** của bài: bài ICML 2024 (venue không công khai review) vẫn có
  điểm review từ lần nộp ICLR trước đó; `bonus_dec` lấy kết quả tốt nhất.
- `compute_quality(..., as_of=T)` chỉ dùng thông tin đã công khai trước T, dùng khi đánh giá theo thời gian:
  review ICLR/TMLR công khai ngay khi đăng; review venue khác chỉ công khai sau decision.
- Khác spec: bỏ `q_cite` (cần citation từ S2); `has_code` là 0/1 thay vì 0/0,1.

## Embedding

Cần `torch`, `transformers`, `adapters` (xem [requirements-features.txt](../requirements-features.txt)).
Thử nhanh: `python -m features embed --limit 200`.
