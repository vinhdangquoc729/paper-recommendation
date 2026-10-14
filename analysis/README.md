# Module: analysis

Đọc `data/corpus.sqlite` (đầu ra của `crawler`) và đo độ thưa của dữ liệu cho từng khối trong spec.

```bash
python -m analysis   # -> reports/sparsity_report.md, reports/sparsity_stats.json
```

| Mục | Câu hỏi | Liên quan spec |
|---|---|---|
| 1 | Corpus bao nhiêu bài, bao nhiêu bài lấy được reference | §2 |
| 2 | Bao nhiêu reference rơi vào corpus | §12.1 (trần ground truth) |
| 3 | Bài trong corpus được trích bao nhiêu lần, hub là gì | §5.3, §6.2 |
| 4 | Bibliographic coupling có phủ được không, bỏ hub thì sao | §6.2, §8.2 |
| 5 | Co-citation trong corpus dày đến đâu | §6.2, chế độ Nền tảng |
| 6 | Giao thức "tác giả là người dùng": bao nhiêu tác giả đủ điều kiện, ground truth to cỡ nào | §12.1 |
| 7 | Bài mới đến đều hay dồn cục theo tuần | V1, digest 7 ngày |
| 8 | Mật độ ma trận người dùng × bài | tổng quan |
| 9 | Đặc trưng cạnh của S2 (intent, isInfluential, contexts) phủ bao nhiêu | V3, có cần GROBID không |
| 10 | OpenReview: review, decision, danh tính | V2 |

Các ngưỡng (ngày cắt T, cửa sổ digest, phân vị hub) đặt ở đầu [sparsity.py](sparsity.py).
