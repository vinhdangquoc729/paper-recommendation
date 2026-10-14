# Hệ gợi ý bài báo khoa học

Bài tập lớn môn Recommender Systems. Corpus hiện tại: ICLR, ICML, NeurIPS, TMLR (2023+). Đặc tả đầy đủ ở [paper-recommender-spec.md](paper-recommender-spec.md).

## Cấu trúc theo module

Mỗi module là một package Python độc lập, có CLI riêng (`python -m <module>`). Các module **chỉ trao đổi
với nhau qua dữ liệu** trong `data/`, không import chéo logic của nhau (trừ `common/`).

| Module | Vai trò | Đọc | Ghi |
|---|---|---|---|
| [common/](common/) | cấu hình, HTTP client có backoff, JSONL, SQLite | | |
| [crawler/](crawler/) | **Module 1**: thu thập dữ liệu từ Semantic Scholar và OpenReview | API | `data/raw/`, `data/corpus.sqlite` |
| [analysis/](analysis/) | phân tích độ thưa của dữ liệu | `data/corpus.sqlite` | `reports/` |
| [features/](features/) | **Module 2**: bảng bài thống nhất, điểm chất lượng, embedding SPECTER2 | `data/corpus.sqlite` | `data/features/` |
| `recsys/` *(sắp làm)* | hồ sơ người dùng, sinh ứng viên, xếp hạng, re-ranking | | |
| `eval/` *(sắp làm)* | giao thức đánh giá, metric, ablation | | |
| `api/`, `app/` *(sắp làm)* | backend, giao diện | | |

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env      # điền tài khoản OpenReview, S2 API key (nếu có)
```

## Chạy

```bash
python -m crawler all          # cào S2: metadata -> reference -> mẫu đặc trưng cạnh -> dựng SQLite
python -m crawler openreview   # cào OpenReview (cần đăng nhập)
python -m crawler load         # dựng lại data/corpus.sqlite sau khi cào thêm
python -m analysis             # -> reports/sparsity_report.md
python -m features all         # items -> quality -> embed (embed cần requirements-features.txt)
python -m unittest discover -s tests -t .
```

Xem chi tiết từng module trong README của module đó.
