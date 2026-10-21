# Module eval: đánh giá offline

Spec mục 12. Giao thức "tác giả là người dùng": quay lại mốc T, coi mỗi tác giả là một người dùng và xem hệ thống
có gợi ý được những bài họ sẽ trích sau T không.

```
data/corpus.sqlite + data/features/ ──► python -m eval run ──► reports/eval/*.md, data/eval/*.csv
```

| Lệnh | Làm gì |
|---|---|
| `gt` | số tác giả và kích thước ground truth theo split, cho cả hai biến thể |
| `run` | chạy các cấu hình (`--methods B0,B1,B2,B3`) trên một split, ghi bảng kết quả và độ đo từng tác giả |
| `ablation` | B4-B8 và bỏ từng thành phần: học trọng số trên train (`--train-authors`, mặc định 2500), chấm trên val; đặc trưng lưu cache ở `data/eval/hybrid_*.npz` (`--rebuild` để tính lại) |

Tham số chung: `--t` (mặc định 2025-01-01), `--split train|val|test` (mặc định val), `--gt all|lead`,
`--limit N` (lấy ngẫu nhiên N tác giả để thử nhanh).

## Giao thức ([protocol.py](protocol.py))

Đơn vị là item của `features` (đã gộp các lần nộp lại), ngày của bài là `first_seen`.

1. **Pool tại T**: mọi bài công khai trước T (cả bài reject, withdrawn), khoảng 37.000 bài với T = 2025-01-01.
2. **Tác giả**: có >= 2 bài trước T, >= 1 bài từ T trở đi, và ground truth không rỗng. Chia train / val / test
   60 / 20 / 20 theo crc32 của OpenReview ID, nên một tác giả luôn ở cùng một split dù đổi T.
3. **Hồ sơ**: bài viết trước T (`authored`) và các bài trong corpus mà những bài đó trích (`cited`).
4. **Ground truth**: bài trong pool được trích ở các bài tác giả viết từ T trở đi, trừ bài đã trích trước T và bài
   của chính tác giả. Dùng **mọi cạnh trích**, không lọc theo trọng số w của V3, để không chấm cấu hình dùng w
   bằng chính thước đo của nó.
   - `all`: mọi bài sau T của tác giả.
   - `lead`: chỉ bài tác giả đứng đầu hoặc cuối, người thường chọn reference. Kết luận nên giữ ở cả hai.
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

## Kết quả hiện tại (T = 2025-01-01, val, 2.364 tác giả)

| | ndcg@10 | recall@20 | mrr | tuổi (ngày) | ild | coverage |
|---|---|---|---|---|---|---|
| B0 random | 0,0004 | 0,0007 | 0,003 | 316 | 0,154 | 0,470 |
| B1 popularity | 0,0684 | 0,0528 | 0,182 | 623 | 0,122 | 0,001 |
| B2 content | 0,0273 | 0,0334 | 0,072 | 264 | 0,058 | 0,224 |
| B3 content đa sở thích | 0,0274 | 0,0333 | 0,073 | 276 | 0,055 | 0,254 |

B1 hơn B2 vì ground truth rất tập trung vào bài nổi tiếng: 22% bài ground truth thuộc top 1% bài được trích nhiều nhất,
trong khi 63% pool chưa được trích lần nào. Nhưng B1 gợi ý gần như cùng một danh sách cho mọi người (coverage 0,1%) và
toàn bài cũ. B2 vẫn đưa bài đúng lên khoảng 11% đầu pool (random: 50%); một vector trung bình làm nhoè các sở thích khác
nhau của tác giả.

B3 không hơn B2 (chênh +0,0001, p = 0,68). Thử trên val: số bài mỗi cụm 3 / 5 / 10, π' sàn 0,5 / 0,8 / 1,0, và chia
suất xen kẽ theo cụm thay cho max: tốt nhất là chia suất xen kẽ (ndcg@10 0,0292, ild 0,078), các cách khác 0,027-0,028,
đều nằm trong khoảng nhiễu. Giới hạn nằm ở tín hiệu nội dung, không ở cách gộp sở thích: ground truth chủ yếu là bài
nổi tiếng mà nội dung không phân biệt được với bài cùng chủ đề ít người trích.

## Ablation từng thành phần ([hybrid.py](hybrid.py), [ablation.py](ablation.py))

Mọi cấu hình kết hợp xếp hạng trên CÙNG tập ứng viên của mỗi tác giả (khoảng 550 bài, hợp top bài theo từng nguồn:
nội dung, độ phổ biến, co-citation, coupling, bài trích tác giả, bài của đồng tác giả). Tập ứng viên chỉ phủ 38%
ground truth, đó là trần của recall. Đặc trưng chuẩn hoá z trong danh sách ứng viên của từng tác giả
([recsys/ranking.py](../recsys/ranking.py)); hàm tuyến tính học trọng số bằng coordinate ascent trên 2.500 tác giả train.

Trọng số cạnh trích dẫn ([features/reference_filter.py](../features/reference_filter.py)), 5 chế độ: `raw` (mọi cạnh
bằng 1), `idf` (chỉ phạt hub), `ctx` (chỉ ngữ cảnh trích dẫn + độ giống nội dung), `w` (cả hai, công thức spec),
`w_theta` (bỏ cạnh w < 0,3, khoảng 28% cạnh). Chế độ ảnh hưởng tới co-citation, coupling và trọng số bài đã trích
trong hồ sơ.

Kết quả T = 2025-01-01, 2.364 tác giả val (`reports/eval/ablation_T2025-01-01_all_s0.md`):

| Cấu hình | ndcg@10 | recall@20 | ild | coverage |
|---|---|---|---|---|
| B1 popularity | 0,068 | 0,053 | 0,122 | 0,1% |
| B3 nội dung đa sở thích | 0,027 | 0,033 | 0,055 | 25% |
| B4 = B3 + đồ thị chưa lọc | 0,061 | 0,062 | 0,084 | 24% |
| B5 = B3 + đồ thị lọc `w` | 0,058 | 0,063 | 0,080 | 25% |
| B5 + độ phổ biến | 0,105 | 0,086 | 0,100 | 5% |
| B5 + độ phổ biến + danh tính | 0,112 | 0,097 | 0,099 | 9% |
| B6 (+ q, tuổi, rel_mean) | 0,115 | 0,102 | 0,093 | 10% |
| B6 với đồ thị chưa lọc | 0,114 | 0,099 | 0,094 | 9% |
| B7 = B6 + MMR λ = 0,5 | 0,115 | 0,102 | 0,095 | 10% |
| B8 LightGBM LambdaRank | **0,121** | **0,111** | 0,103 | 13% |

Bỏ từng thành phần khỏi B6 (ndcg@10): độ phổ biến −0,039; danh tính −0,007; co-citation −0,007; nội dung đa sở thích
−0,003; tuổi −0,002; coupling −0,002; rel_mean, q ≈ 0.

Nhận xét:
- Đồ thị trích dẫn là tín hiệu mạnh nhất sau độ phổ biến: thêm vào nội dung tăng ndcg@10 từ 0,027 lên 0,061.
- **Lọc reference (V3) không giúp với ground truth này**: so với đồ thị chưa lọc, `ctx` ngang (−0,0003, p = 0,68),
  `idf` / `w` / `w_theta` kém hơn ít nhưng có ý nghĩa; trong cấu hình đủ (B6) chênh +0,0014, p = 0,88. Lý do khả dĩ:
  ground truth gồm MỌI lần trích, kể cả trích cho có và trích bài nổi tiếng, nên phạt hub hay bỏ cạnh yếu làm mất đúng
  thứ ground truth thưởng. Câu hỏi "lọc có tìm ra bài thực sự liên quan hơn không" cần thước đo khác (nhãn tay, spec 5.3).
- MMR gần như không đổi gì: SPECTER2 cho cosine giữa các bài cùng lĩnh vực dồn trong khoảng hẹp, nên phạt trùng lặp
  nhỏ so với chênh lệch điểm.
- Độ phổ biến tăng độ chính xác nhưng kéo coverage từ 25% xuống 5% và tăng tuổi bài: đánh đổi cần nêu trong báo cáo.

## Hạn chế

- Trích dẫn chỉ là proxy cho quan tâm: số tuyệt đối thấp hơn thực tế, chỉ nên đọc chênh lệch giữa các cấu hình.
- Chỉ bài có reference (bài trên arXiv, chủ yếu bài accept) mới tạo ground truth.
- Reference lấy từ bản arXiv mới nhất, có thể được sửa sau T, nên hồ sơ và B1 có thể biết thêm vài cạnh từ sau T.
