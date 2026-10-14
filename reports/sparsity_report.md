# Báo cáo độ thưa dữ liệu

_Sinh tự động bởi `python -m analysis`, ngày 2026-10-12._


## 1. Tổng quan corpus (Semantic Scholar, bài đã accept)

| venue   | edition   |   số bài | có abstract   | có arXiv   | có ngày công bố   | refs ok   | refs bị ẩn   | refs rỗng/không thấy   | chưa cào refs   |   median #refs (bài ok) |   median citation |
|:--------|:----------|---------:|:--------------|:-----------|:------------------|:----------|:-------------|:-----------------------|:----------------|------------------------:|------------------:|
| iclr    | 2023      |     1675 | 79.3%         | 79.1%      | 79.2%             | 78.3%     | 16.4%        | 5.4%                   | 0.0%            |                   57.00 |             28.00 |
| iclr    | 2024      |     2516 | 82.1%         | 82.1%      | 82.2%             | 35.6%     | 52.6%        | 11.8%                  | 0.0%            |                   56.00 |             20.00 |
| iclr    | 2025      |     2925 | 67.0%         | 66.7%      | 67.0%             | 7.0%      | 61.7%        | 31.3%                  | 0.0%            |                   57.00 |             10.00 |
| iclr    | 2026      |       19 | 100.0%        | 73.7%      | 73.7%             | 5.3%      | 68.4%        | 26.3%                  | 0.0%            |                   31.00 |              2.00 |
| icml    | 2023      |     1800 | 83.4%         | 83.2%      | 83.4%             | 82.7%     | 16.4%        | 0.9%                   | 0.0%            |                   55.00 |             18.00 |
| icml    | 2024      |     2678 | 80.2%         | 80.1%      | 80.2%             | 30.6%     | 52.4%        | 17.1%                  | 0.0%            |                   55.00 |             13.00 |
| icml    | 2025      |     3072 | 73.3%         | 73.1%      | 73.3%             | 1.8%      | 67.9%        | 30.3%                  | 0.0%            |                   53.00 |              7.00 |
| icml    | 2026      |        2 | 100.0%        | 100.0%     | 100.0%            | 0.0%      | 100.0%       | 0.0%                   | 0.0%            |                  nan    |              8.50 |
| neurips | 2023      |     3522 | 95.6%         | 79.1%      | 79.3%             | 78.6%     | 16.8%        | 4.6%                   | 0.0%            |                   57.00 |             22.00 |
| neurips | 2024      |     4501 | 95.3%         | 80.6%      | 80.8%             | 26.9%     | 64.8%        | 8.3%                   | 0.0%            |                   59.00 |             15.00 |
| neurips | 2025      |     5652 | 96.1%         | 78.2%      | 78.4%             | 0.6%      | 91.8%        | 7.6%                   | 0.0%            |                   49.00 |              5.00 |
| tmlr    | 2023      |      555 | 74.4%         | 73.9%      | 74.4%             | 74.2%     | 24.3%        | 1.4%                   | 0.0%            |                   60.00 |              9.00 |
| tmlr    | 2024      |     1005 | 75.3%         | 75.2%      | 75.3%             | 48.1%     | 43.2%        | 8.8%                   | 0.0%            |                   59.00 |              5.00 |
| tmlr    | 2025      |     1446 | 72.7%         | 72.6%      | 72.7%             | 14.7%     | 74.5%        | 10.9%                  | 0.0%            |                   61.00 |              3.00 |
| tmlr    | 2026      |     1070 | 54.7%         | 54.6%      | 54.7%             | 3.1%      | 64.5%        | 32.4%                  | 0.0%            |                   55.00 |              0.00 |
| TỔNG    |           |    32438 | 83.8%         | 76.7%      | 76.9%             | 30.6%     | 56.2%        | 13.2%                  | 0.0%            |                   57.00 |             10.00 |


### Số bài mỗi tác giả (S2 author ID)

- số tác giả: **93,284**
- chỉ có 1 bài: **65.0%**
- ≥ 3 bài: **16,140 (17.3%)**
- ≥ 5 bài: **5,607 (6.0%)**

> Lưu ý: S2 hay tách một người thành nhiều author ID, nên số liệu tác giả là cận dưới về độ dày hồ sơ.


## 2. Reference: phân giải được bao nhiêu, rơi vào corpus bao nhiêu

- bài có reference: **9,922**
- tổng số cạnh reference: **569,838**
- S2 phân giải được (có paperId): **98.4%**
- cạnh trỏ vào corpus: **28,733 (5.0%)**

Tỉ lệ cạnh trỏ vào corpus là **trần** cho mọi ground truth dạng "tác giả trích bài nào trong corpus": phần còn lại là bài ngoài các venue trong corpus.


### Số reference trong corpus của mỗi bài (out-degree nội corpus)

| venue   |   edition |   mean |   median |   p90 | % bài = 0   |
|:--------|----------:|-------:|---------:|------:|:------------|
| iclr    |      2023 |   1.62 |     0.00 |  5.00 | 56.6%       |
| iclr    |      2024 |   4.01 |     3.00 |  9.00 | 15.9%       |
| iclr    |      2025 |   6.87 |     5.00 | 14.70 | 6.4%        |
| iclr    |      2026 |   3.00 |     3.00 |  3.00 | 0.0%        |
| icml    |      2023 |   1.03 |     0.00 |  3.00 | 56.7%       |
| icml    |      2024 |   4.76 |     4.00 | 11.00 | 14.2%       |
| icml    |      2025 |   4.59 |     2.50 | 11.00 | 13.0%       |
| neurips |      2023 |   1.75 |     1.00 |  5.00 | 37.6%       |
| neurips |      2024 |   6.11 |     4.00 | 14.00 | 11.3%       |
| neurips |      2025 |   3.25 |     1.50 |  5.90 | 34.4%       |
| tmlr    |      2023 |   1.61 |     0.00 |  4.00 | 53.4%       |
| tmlr    |      2024 |   3.60 |     2.00 |  8.00 | 27.7%       |
| tmlr    |      2025 |   4.97 |     3.00 | 13.00 | 11.8%       |
| tmlr    |      2026 |   4.94 |     2.00 | 11.00 | 33.3%       |


## 3. Bài trong corpus được trích bao nhiêu lần (trong corpus) và hub

| venue   |   edition |   mean |   median | % chưa ai trích   | % ≥ 5 lần   |
|:--------|----------:|-------:|---------:|:------------------|:------------|
| iclr    |      2023 |   4.54 |     2.00 | 28.2%             | 25.0%       |
| iclr    |      2024 |   1.12 |     0.00 | 67.4%             | 5.8%        |
| iclr    |      2025 |   0.09 |     0.00 | 94.5%             | 0.2%        |
| iclr    |      2026 |   0.00 |     0.00 | 100.0%            | 0.0%        |
| icml    |      2023 |   3.23 |     1.00 | 36.0%             | 17.2%       |
| icml    |      2024 |   0.61 |     0.00 | 74.2%             | 2.9%        |
| icml    |      2025 |   0.02 |     0.00 | 98.2%             | 0.0%        |
| icml    |      2026 |   0.00 |     0.00 | 100.0%            | 0.0%        |
| neurips |      2023 |   2.18 |     1.00 | 49.1%             | 10.8%       |
| neurips |      2024 |   0.21 |     0.00 | 86.7%             | 0.5%        |
| neurips |      2025 |   0.01 |     0.00 | 99.5%             | 0.0%        |
| tmlr    |      2023 |   2.23 |     0.00 | 52.4%             | 9.5%        |
| tmlr    |      2024 |   0.48 |     0.00 | 82.0%             | 2.1%        |
| tmlr    |      2025 |   0.09 |     0.00 | 95.0%             | 0.4%        |
| tmlr    |      2026 |   0.01 |     0.00 | 99.3%             | 0.0%        |

Bài chưa được trích trong corpus thì **không có co-citation** và không có tín hiệu citation velocity.


### Hub (reference được trích nhiều nhất)

- số reference khác nhau: **157,873**
- reference chỉ được 1 bài trích: **59.5%**
- ngưỡng hub (phân vị 99.9%): **≥ 162 bài trích**
- số hub: **158**
- tỉ lệ cạnh trỏ vào hub: **10.3%**

| cited_id                                 |   số bài trích | trong corpus?    |
|:-----------------------------------------|---------------:|:-----------------|
| 204e3073870fae3d05bcbc2f6a8e263d9b72e776 |           1836 | — (ngoài corpus) |
| 2c03df8b48bf3fa39054345bafabfeff15bfd11d |           1772 | — (ngoài corpus) |
| 90abbc2cf38462b954ae1b772fac9532e2ccd8b0 |           1536 | — (ngoài corpus) |
| 5d90f06bb70a0a3dced62413346235c02b1aa086 |           1275 | — (ngoài corpus) |
| 6f870f7f02a8c59c3e23f407f3ef00dd1dcf8fc4 |           1264 | — (ngoài corpus) |
| 268d347e8a55b5eb82fb5e7d2f800e33c75ab18a |           1215 | — (ngoài corpus) |
| a6cb366736791bcccc5c8639de5a8f9636bf87e8 |           1133 | — (ngoài corpus) |
| df2b0e26d0599ce3e70df8a9da02e51594e0e992 |           1075 | — (ngoài corpus) |
| d2c733e34d48784a37d717fe43d9e93277a8c53e |           1072 | — (ngoài corpus) |
| 3c8a456509e6c0805354bd40a35e3f2dbf8069b1 |           1004 | — (ngoài corpus) |


## 4. Bibliographic coupling (chung reference, kể cả reference ngoài corpus)

| biến thể      | chi phí Σ deg_in²   | % bài có ≥1 láng giềng   |   median #láng giềng (≥1 ref chung) | % bài có ≥10 láng giềng chung ≥2 ref   |   median #láng giềng (≥2 ref chung) |
|:--------------|:--------------------|:-------------------------|------------------------------------:|:---------------------------------------|------------------------------------:|
| mọi reference | 45,425,085          | 100.0%                   |                             2265.00 | 98.9%                                  |                              712.50 |
| bỏ hub        | 10,458,424          | 100.0%                   |                              524.00 | 98.2%                                  |                              155.00 |


### Theo edition (bỏ hub, láng giềng chung ≥ 2 reference)

| venue   |   edition |   median #láng giềng ≥2 ref | % ≥10   | % = 0   |
|:--------|----------:|----------------------------:|:--------|:--------|
| iclr    |      2023 |                      182.00 | 99.7%   | 0.0%    |
| iclr    |      2024 |                      174.00 | 99.6%   | 0.0%    |
| iclr    |      2025 |                      143.50 | 98.0%   | 1.0%    |
| iclr    |      2026 |                       28.00 | 100.0%  | 0.0%    |
| icml    |      2023 |                      144.00 | 97.6%   | 0.1%    |
| icml    |      2024 |                      147.00 | 97.6%   | 0.5%    |
| icml    |      2025 |                      107.00 | 96.3%   | 0.0%    |
| neurips |      2023 |                      149.00 | 98.2%   | 0.1%    |
| neurips |      2024 |                      143.50 | 97.1%   | 0.2%    |
| neurips |      2025 |                       71.50 | 93.8%   | 0.0%    |
| tmlr    |      2023 |                      164.50 | 99.0%   | 0.0%    |
| tmlr    |      2024 |                      170.00 | 98.6%   | 0.2%    |
| tmlr    |      2025 |                      160.50 | 97.6%   | 0.0%    |
| tmlr    |      2026 |                       75.00 | 97.0%   | 0.0%    |

Coupling chỉ cần reference của chính bài nên **dùng được ngay cho bài mới** (miễn S2 trả reference).


## 5. Co-citation trong corpus

| venue   |   edition | % có ≥1 bài đồng trích   |   median #đồng trích | % có bài đồng trích ≥2 lần   |
|:--------|----------:|:-------------------------|---------------------:|:-----------------------------|
| iclr    |      2023 | 67.0%                    |                 5.00 | 35.3%                        |
| iclr    |      2024 | 32.0%                    |                 0.00 | 13.2%                        |
| iclr    |      2025 | 5.3%                     |                 0.00 | 1.1%                         |
| iclr    |      2026 | 0.0%                     |                 0.00 | 0.0%                         |
| icml    |      2023 | 59.6%                    |                 2.00 | 27.0%                        |
| icml    |      2024 | 25.4%                    |                 0.00 | 8.5%                         |
| icml    |      2025 | 1.7%                     |                 0.00 | 0.0%                         |
| icml    |      2026 | 0.0%                     |                 0.00 | 0.0%                         |
| neurips |      2023 | 48.1%                    |                 0.00 | 20.5%                        |
| neurips |      2024 | 12.9%                    |                 0.00 | 2.9%                         |
| neurips |      2025 | 0.5%                     |                 0.00 | 0.1%                         |
| tmlr    |      2023 | 44.0%                    |                 0.00 | 16.6%                        |
| tmlr    |      2024 | 16.8%                    |                 0.00 | 4.8%                         |
| tmlr    |      2025 | 4.8%                     |                 0.00 | 1.3%                         |
| tmlr    |      2026 | 0.7%                     |                 0.00 | 0.1%                         |

Co-citation chỉ tính từ bài citing **trong corpus**. Muốn dày hơn phải lấy citation từ toàn bộ S2 (endpoint /citations, tốn thêm nhiều request).


## 6. Giao thức "tác giả là người dùng" (Mục 12.1 trong spec)

- Hồ sơ tại T: bài `authored` có ngày < T.
- Ground truth (GT): bài trong corpus được trích bởi bài của tác giả đăng ≥ T, loại bài đã trích trước T và bài của chính tác giả.
- GT nghiêm: bỏ thêm cạnh tự trích (bài citing và cited có chung tác giả bất kỳ, tức gồm cả trích bài của đồng tác giả).
- GT digest Δ: chỉ giữ GT có ngày trong [T, T+Δ).
- Ngày của bài = `publicationDate` trên S2 (thường là ngày lên arXiv).


### Số tác giả đủ điều kiện

| T          | ≥3 bài & ≥1 sau T (spec)   | + ≥1 bài trước T   | + ≥2 bài trước T   |
|:-----------|:---------------------------|:-------------------|:-------------------|
| 2024-07-01 | 13,784                     | 11,107             | 7,368              |
| 2025-01-01 | 11,731                     | 10,867             | 8,627              |
| 2025-07-01 | 6,221                      | 6,109              | 5,589              |


### Kích thước ground truth mỗi tác giả (trên tập đủ điều kiện có ≥1 bài trước T)

| T          | loại                   | % tác giả có GT ≥1   | % có GT ≥5   |   mean |   median | trần: % ref sau T thuộc corpus   | % tác giả có bài sau T lấy được refs   |
|:-----------|:-----------------------|:---------------------|:-------------|-------:|---------:|:---------------------------------|:---------------------------------------|
| 2024-07-01 | GT                     | 4.3%                 | 2.7%         |   0.34 |     0.00 | 13.5%                            | 4.6%                                   |
| 2024-07-01 | GT nghiêm              | 4.2%                 | 2.4%         |   0.32 |     0.00 |                                  |                                        |
| 2024-07-01 | GT digest 30d (nghiêm) | 0.9%                 | 0.0%         |   0.01 |     0.00 |                                  |                                        |
| 2024-07-01 | GT digest 90d (nghiêm) | 1.3%                 | 0.0%         |   0.02 |     0.00 |                                  |                                        |
| 2025-01-01 | GT                     | 1.5%                 | 0.7%         |   0.10 |     0.00 | 11.6%                            | 1.6%                                   |
| 2025-01-01 | GT nghiêm              | 1.4%                 | 0.7%         |   0.09 |     0.00 |                                  |                                        |
| 2025-01-01 | GT digest 30d (nghiêm) | 0.0%                 | 0.0%         |   0.00 |     0.00 |                                  |                                        |
| 2025-01-01 | GT digest 90d (nghiêm) | 0.1%                 | 0.0%         |   0.00 |     0.00 |                                  |                                        |
| 2025-07-01 | GT                     | 0.1%                 | 0.0%         |   0.00 |     0.00 | 2.8%                             | 0.2%                                   |
| 2025-07-01 | GT nghiêm              | 0.1%                 | 0.0%         |   0.00 |     0.00 |                                  |                                        |
| 2025-07-01 | GT digest 30d (nghiêm) | 0.0%                 | 0.0%         |   0.00 |     0.00 |                                  |                                        |
| 2025-07-01 | GT digest 90d (nghiêm) | 0.0%                 | 0.0%         |   0.00 |     0.00 |                                  |                                        |


## 7. Luồng bài mới theo tuần (ảnh hưởng tới digest 7 ngày)


### Theo ngày S2 (publicationDate, thường là ngày lên arXiv)

- số tuần: **197**
- median bài/tuần: **88**
- % tuần < 20 bài: **20.3%**
- % bài rơi vào 5 tuần đông nhất: **16.8%**
- 5 tuần đông nhất: **2025-12-01 (1,286), 2025-04-28 (1,081), 2025-05-26 (994), 2024-11-25 (962), 2025-06-30 (961)**


### Theo ngày công khai trên OpenReview (odate → pdate → cdate)

- số tuần: **216**
- median bài/tuần: **35**
- % tuần < 20 bài: **19.9%**
- % bài rơi vào 5 tuần đông nhất: **64.5%**
- 5 tuần đông nhất: **2025-10-06 (19,747), 2024-09-30 (11,684), 2023-10-09 (7,285), 2026-06-22 (6,445), 2025-10-27 (5,339)**


## 8. Độ dày ma trận người dùng × bài báo

- người dùng (tác giả): **93,284**
- bài báo: **32,438**
- tương tác (authored ∪ cited trong corpus): **323,722**
- mật độ: **1.07e-04**
- median tương tác / người dùng: **1**
- median tương tác / tác giả ≥3 bài: **6**


## 9. Đặc trưng cạnh từ S2 (mẫu): đủ để lọc reference nhiễu (V3) không?

- số bài trong mẫu: **300**
- bài bị ẩn reference ở endpoint này: **0.0%**
- số cạnh: **18,583**
- isInfluential = true: **13.9%**
- có ít nhất 1 intent: **62.2%**
- có ít nhất 1 context: **81.6%**
- chỉ đúng 1 context: **48.5%**
- ≥ 3 context (nhắc nhiều lần): **17.5%**
- phân bố intent: **background: 43.4%, methodology: 29.9%, result: 2.2%**

Số context xấp xỉ `mention_count` trong spec; nếu độ phủ context cao thì có thể bỏ GROBID.


## 10. OpenReview: review, decision, danh tính tác giả

| venue   |   edition |   submission | thấy tác giả   | có review   | có rating số   | accept   | reject   | withdrawn   | chưa rõ   | nối được sang S2   |
|:--------|----------:|-------------:|:---------------|:------------|:---------------|:---------|:---------|:------------|:----------|:-------------------|
| iclr    |      2023 |         3792 | 100.0%         | 100.0%      | 100.0%         | 41.5%    | 58.5%    | 0.0%        | 0.0%      | 30.8%              |
| iclr    |      2024 |         7404 | 100.0%         | 98.1%       | 98.1%          | 30.5%    | 47.5%    | 21.2%       | 0.0%      | 29.9%              |
| iclr    |      2025 |        11672 | 100.0%         | 98.7%       | 98.7%          | 31.8%    | 43.0%    | 24.6%       | 0.0%      | 31.0%              |
| iclr    |      2026 |        19814 | 100.0%         | 98.3%       | 98.3%          | 27.0%    | 44.5%    | 23.9%       | 0.0%      | 0.1%               |
| icml    |      2023 |         1828 | 100.0%         | 0.0%        | 0.0%           | 100.0%   | 0.0%     | 0.0%        | 0.0%      | 89.0%              |
| icml    |      2024 |         2610 | 100.0%         | 0.0%        | 0.0%           | 100.0%   | 0.0%     | 0.0%        | 0.0%      | 96.4%              |
| icml    |      2025 |         3422 | 100.0%         | 100.0%      | 100.0%         | 95.3%    | 4.7%     | 0.0%        | 0.0%      | 92.6%              |
| icml    |      2026 |         6555 | 100.0%         | 100.0%      | 100.0%         | 96.7%    | 3.3%     | 0.0%        | 0.0%      | 0.0%               |
| neurips |      2023 |         3395 | 100.0%         | 100.0%      | 100.0%         | 94.8%    | 5.2%     | 0.0%        | 0.0%      | 90.2%              |
| neurips |      2024 |         4236 | 100.0%         | 100.0%      | 100.0%         | 95.3%    | 4.7%     | 0.0%        | 0.0%      | 92.7%              |
| neurips |      2025 |         5540 | 100.0%         | 100.0%      | 100.0%         | 95.4%    | 4.6%     | 0.0%        | 0.0%      | 91.4%              |
| tmlr    |      2022 |          441 | 49.4%          | 99.1%       | 0.0%           | 49.0%    | 44.9%    | 6.1%        | 0.0%      | 2.9%               |
| tmlr    |      2023 |          958 | 64.5%          | 98.9%       | 0.0%           | 63.8%    | 31.4%    | 4.8%        | 0.0%      | 47.0%              |
| tmlr    |      2024 |         1435 | 67.0%          | 98.7%       | 0.0%           | 66.6%    | 29.5%    | 4.0%        | 0.0%      | 65.3%              |
| tmlr    |      2025 |         2133 | 67.3%          | 98.4%       | 0.0%           | 67.2%    | 28.0%    | 4.5%        | 0.3%      | 65.9%              |
| tmlr    |      2026 |         3431 | 48.6%          | 85.5%       | 0.0%           | 52.9%    | 10.9%    | 3.0%        | 33.1%     | 37.7%              |


## 11. Reference từ source LaTeX trên arXiv (.bbl)

- số bài đã tải: **130**
- trạng thái: **ok: 87.7%, no_bbl: 12.3%**
- thời gian thực tế / bài: **7.1 s (median 3.6 s)**
- dung lượng gói source (median): **2.9 MB**
- số reference / bài có .bbl (median): **59**
- tỉ lệ so với referenceCount của S2 (median): **1.00**
- reference tách được tiêu đề: **99.4%**
- reference có arXiv ID: **24.8%**
- reference khớp vào corpus: **10.8% (theo arXiv ID 3.9%, theo tiêu đề 6.9%)**


### Đối chiếu với S2 trên 29 bài S2 có reference (cạnh trỏ vào corpus)

- cạnh theo S2: **101**
- cạnh theo .bbl: **95**
- precision (.bbl đúng theo S2): **97.9%**
- recall (.bbl tìm lại được cạnh của S2): **92.1%**


### Ước lượng nếu chạy cho toàn bộ bài bị S2 ẩn

- bài bị ẩn: **18,239**
- trong đó có arXiv ID: **14,096 (77.3%)**
- thời gian ước tính: **~27.8 giờ ở tốc độ hiện tại**
- bài bị ẩn lấy lại được reference (trong mẫu): **84.8%**
- cạnh vào corpus / bài (mẫu bị ẩn, từ .bbl): **7.9**
