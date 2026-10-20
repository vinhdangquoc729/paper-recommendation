# Hệ gợi ý bài báo khoa học

Corpus hiện tại: ICLR, ICML, NeurIPS, TMLR (2023+). Đặc tả đầy đủ ở [paper-recommender-spec.md](paper-recommender-spec.md).

## Kiến trúc

Mỗi module là một package Python độc lập, có CLI riêng (`python -m <module>`). Các module **chỉ trao đổi
với nhau qua dữ liệu** trong `data/`, không import chéo logic của nhau (trừ `common/`).

| Module | Vai trò | Đọc | Ghi |
|---|---|---|---|
| [common/](common/) | cấu hình, HTTP client có backoff, JSONL, SQLite | | |
| [crawler/](crawler/) | thu thập dữ liệu từ Semantic Scholar và OpenReview | API | `data/raw/`, `data/corpus.sqlite` |
| [analysis/](analysis/) | phân tích dữ liệu | `data/corpus.sqlite` | `reports/` |
| [features/](features/) | bảng bài thống nhất, điểm chất lượng, embedding SPECTER2 | `data/corpus.sqlite` | `data/features/` |
| `recsys/` | hồ sơ người dùng, sinh ứng viên, xếp hạng, re-ranking | | |
| `eval/` | giao thức đánh giá, metric, ablation | | |
| [api/](api/) | backend FastAPI | `data/features/`, `data/corpus.sqlite` | `data/app.sqlite` |
| [app/](app/) | giao diện React: Bài báo, Đọc bài, Tài khoản | API | |

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env      # điền tài khoản OpenReview, S2 API key (nếu có)
```

## Chạy

```bash
python -m crawler all          # cào S2: metadata -> reference -> mẫu đặc trưng cạnh -> dựng SQLite
python -m crawler openreview   # cào OpenReview (cần đăng nhập)
python -m crawler corpus-refs  # reference từ source LaTeX arXiv 
python -m crawler load         # dựng lại data/corpus.sqlite sau khi cào thêm
python -m analysis             # -> reports/sparsity_report.md
python -m features all         # items -> quality -> embed (embed cần requirements-features.txt)
python -m api                  # backend tại http://127.0.0.1:8000 (tài liệu: /docs)
cd app && npm install && npm run dev   # giao diện tại http://localhost:5173
python -m unittest discover -s tests -t .
```

Xem chi tiết từng module trong README của module đó.
