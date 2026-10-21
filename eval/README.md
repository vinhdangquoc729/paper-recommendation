# Module eval: đánh giá offline

Spec mục 12. Giao thức "tác giả là người dùng": quay lại mốc T, coi mỗi tác giả là một người dùng và xem hệ thống
có gợi ý được những bài họ sẽ trích sau T không.

```
data/corpus.sqlite + data/features/ ──► python -m eval run ──► reports/eval/*.md, data/eval/*.csv
```

| Lệnh | Làm gì |
|---|---|
| `gt` | số tác giả và kích thước ground truth theo split, cho các biến thể |
| `run` | chạy các cấu hình (`--methods B0,B1,B2,B3`) trên một split, ghi bảng kết quả và độ đo từng tác giả |
| `ablation` | B4-B8 và bỏ từng thành phần: học trọng số trên train (`--train-authors`, mặc định 2500), chấm trên val; đặc trưng lưu cache ở `data/eval/hybrid_*.npz` (`--rebuild` để tính lại) |

Tham số chung: `--t` (mặc định 2025-01-01), `--split train|val|test` (mặc định val), `--gt all|lead|novel`,
`--limit N` (lấy ngẫu nhiên N tác giả để thử nhanh).

## Giao thức ([protocol.py](protocol.py))

Đơn vị là item của `features` (đã gộp các lần nộp lại), ngày của bài là `first_seen`.

1. **Pool tại T**: mọi bài công khai trước T (cả bài reject, withdrawn).
2. **Tác giả**: có >= 2 bài trước T, >= 1 bài từ T trở đi, và ground truth không rỗng. Chia train / val / test
   60 / 20 / 20 theo crc32 của OpenReview ID, nên một tác giả luôn ở cùng một split dù đổi T.
3. **Hồ sơ**: bài viết trước T (`authored`) và các bài trong corpus mà những bài đó trích (`cited`).
4. **Ground truth**: bài trong pool được trích ở các bài tác giả viết từ T trở đi, trừ bài đã trích trước T và bài
   của chính tác giả. Dùng **mọi cạnh trích**, không lọc theo trọng số w của V3, để không chấm cấu hình dùng w
   bằng chính thước đo của nó.
   - `all`: mọi bài sau T của tác giả.
   - `lead`: chỉ bài tác giả đứng đầu hoặc cuối, người thường chọn reference.
   - `novel`: như `all`, bỏ thêm bài có tác giả là cộng sự trước T (trích trong nhóm làm phồng đặc trưng đồng tác giả).
5. **Chống rò rỉ**: số lần được trích (B1) chỉ đếm từ bài công khai trước T; q_p tính bằng
   `compute_quality(as_of=T)`.

## Chấm điểm ([run.py](run.py), [metrics.py](metrics.py))

Mỗi cấu hình trả điểm cho **toàn bộ pool** (không lấy mẫu bài âm). Bài tác giả đã viết hoặc đã trích bị loại trước khi
xếp hạng, giống nhau cho mọi cấu hình.

| Độ đo | Ý nghĩa |
|---|---|
| `recall@k`, `ndcg@k` (k = 10, 20) | độ chính xác, nhãn nhị phân |
| `mrr` | 1 / vị trí của bài đúng đầu tiên trong toàn bộ xếp hạng |
| `age_days`, `new@30d` | tuổi trung bình của top-10 tại T; tỉ lệ bài < 30 ngày (V1) |
| `q` | q_p trung bình của top-10 (V2) |
| `ild` | khoảng cách trung bình 1 - cos giữa các cặp trong top-10 (đa dạng) |
| `coverage` | tỉ lệ pool xuất hiện trong ít nhất một top-10 |

Bảng kết quả có khoảng tin cậy 95% của `ndcg@10` (bootstrap theo tác giả) và so sánh cặp mỗi cấu hình với cấu hình
đầu tiên trong `--methods` (chênh lệch, CI 95%, p của Wilcoxon).

## Baseline ([baselines.py](baselines.py))

| # | Cấu hình |
|---|---|
| B0 | random |
| B1 | popularity: số bài công khai trước T trích bài đó |
| B2 | content: hồ sơ là một vector, trung bình có trọng số SPECTER2 (viết 1,0, đứng đầu x1,2, trích 0,5; decay 3 năm) |
| B3 | content đa sở thích: cùng tập bài, phân cụm tối đa 5 sở thích ([recsys/profile.py](../recsys/profile.py)), điểm max_c π'_c · cos |

## Ablation từng thành phần ([hybrid.py](hybrid.py), [ablation.py](ablation.py))

Mọi cấu hình kết hợp xếp hạng trên CÙNG tập ứng viên của mỗi tác giả (hợp top bài theo từng nguồn:
nội dung, độ phổ biến, co-citation, coupling, bài trích tác giả, bài của đồng tác giả). Độ phủ ground truth của tập ứng viên
là trần của recall. Đặc trưng chuẩn hoá z trong danh sách ứng viên của từng tác giả
([recsys/ranking.py](../recsys/ranking.py)); hàm tuyến tính học trọng số bằng coordinate ascent trên tác giả train.

Trọng số cạnh trích dẫn ([features/reference_filter.py](../features/reference_filter.py)), 5 chế độ: `raw` (mọi cạnh
bằng 1), `idf` (chỉ phạt hub), `ctx` (chỉ ngữ cảnh trích dẫn + độ giống nội dung), `w` (cả hai, công thức spec),
`w_theta` (bỏ cạnh w < 0,3). Chế độ ảnh hưởng tới co-citation, coupling và trọng số bài đã trích
trong hồ sơ.

Kết quả từng lần chạy ghi ở `reports/eval/`.

## Hạn chế

- Trích dẫn chỉ là proxy cho quan tâm: số tuyệt đối thấp hơn thực tế, chỉ nên đọc chênh lệch giữa các cấu hình.
- Chỉ bài có reference (bài trên arXiv, chủ yếu bài accept) mới tạo ground truth.
- Reference lấy từ bản arXiv mới nhất, có thể được sửa sau T, nên hồ sơ và B1 có thể biết thêm vài cạnh từ sau T.
