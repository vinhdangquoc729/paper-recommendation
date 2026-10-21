# Hệ gợi ý bài báo khoa học

Corpus hiện tại: ICLR, ICML, NeurIPS, TMLR (2023+). Đặc tả đầy đủ ở [paper-recommender-spec.md](paper-recommender-spec.md).

## Kiến trúc

Mỗi module là một package Python độc lập, có CLI riêng (`python -m <module>`). Các module **chỉ trao đổi
với nhau qua dữ liệu** trong `data/`, không import chéo logic của nhau (trừ `common/`). Ngoại lệ: `eval/` gọi
thẳng code của `features/` và `recsys/` để tính lại mọi thứ tại mốc T, đúng như sản phẩm chạy; `api/` dùng `recsys/` và `appdb/`.

| Module | Vai trò | Đọc | Ghi |
|---|---|---|---|
| [common/](common/) | cấu hình, HTTP client có backoff, JSONL, SQLite | | |
| [crawler/](crawler/) | thu thập dữ liệu từ Semantic Scholar và OpenReview | API | `data/raw/`, `data/corpus.sqlite` |
| [analysis/](analysis/) | phân tích dữ liệu | `data/corpus.sqlite` | `reports/` |
| [features/](features/) | bảng bài thống nhất, điểm chất lượng, embedding SPECTER2 | `data/corpus.sqlite` | `data/features/` |
| [recsys/](recsys/) | lõi gợi ý: hồ sơ, sinh ứng viên, đặc trưng, xếp hạng, MMR (dùng chung cho sản phẩm và đánh giá) | | |
| [appdb/](appdb/) | CSDL sản phẩm (Postgres + pgvector): catalog, tài khoản (mỗi tác giả một tài khoản tạo sẵn), hành vi | `data/` | Postgres |
| [eval/](eval/) | đánh giá offline "tác giả là người dùng", metric, baseline | `data/corpus.sqlite`, `data/features/` | `reports/eval/`, `data/eval/` |
| [api/](api/) | backend FastAPI: đăng nhập, gợi ý, phản hồi | Postgres, `data/models/` | Postgres |
| [app/](app/) | giao diện React: Bài báo, Đọc bài, Tài khoản, Đăng nhập | API | |

## Cài đặt

```bash
pip install -r requirements.txt
cp .env.example .env      # điền tài khoản OpenReview, S2 API key (nếu có)
```

## Chạy

```bash
python -m crawler all          # cào S2: metadata -> reference -> mẫu đặc trưng cạnh -> dựng SQLite
python -m crawler openreview   # cào OpenReview (cần đăng nhập)
python -m crawler corpus-refs  # reference từ arXiv (HTML, không có thì source LaTeX)
python -m crawler load         # dựng lại data/corpus.sqlite sau khi cào thêm
python -m analysis             # -> reports/sparsity_report.md
python -m features all         # items -> quality -> embed (embed cần requirements-features.txt)
python -m eval run             # đánh giá B0-B3 trên tập val -> reports/eval/
python -m eval ablation --objective graded    # B4-B8, ablation; xuất mô hình data/models/linear_b6_graded.json
docker compose up -d db        # Postgres (cổng 55432)
python -m appdb migrate && python -m appdb sync   # lược đồ, nạp catalog, tạo sẵn tài khoản tác giả
python -m api                  # backend tại http://127.0.0.1:8000 (tài liệu: /docs)
cd app && npm install && npm run dev   # giao diện tại http://localhost:5173
python -m unittest discover -s tests -t .
```

Chạy cả sản phẩm bằng Docker (giao diện tại http://localhost:8080, cần `data/models/linear_b6.json` và DB đã sync):

```bash
docker compose up -d --build
```

Xem chi tiết từng module trong README của module đó.
