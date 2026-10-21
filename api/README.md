# Module api (backend FastAPI)

```
Postgres (appdb: catalog + người dùng) ─► python -m api ─► http://127.0.0.1:8000/api/...
data/models/linear_b6.json (mô hình)  ─┘
```

Khi khởi động: nạp catalog từ Postgres vào bộ nhớ và dựng bộ gợi ý ([recsys/service.py](../recsys/service.py)); dữ liệu
người dùng đọc / ghi thẳng vào Postgres. Phiên đăng nhập là cookie `session` (httponly, 30 ngày).
Cần `docker compose up -d db`, `python -m appdb migrate`, `python -m appdb sync` trước.
Tài liệu tương tác: http://127.0.0.1:8000/docs.

| Method | Đường dẫn | Dùng ở màn | Mô tả |
|---|---|---|---|
| GET | `/api/session` | cả 3 | đang đăng nhập là ai (`logged_in` = false nếu chưa) |
| POST | `/api/session/author` | Đăng nhập | bản demo: mở tài khoản tạo sẵn của một tác giả (`openreview_id`), không xác minh |
| POST | `/api/session/login`, `/api/session/register` | Đăng nhập | tài khoản email + mật khẩu (>= 8 ký tự) |
| DELETE | `/api/session` | thanh tiêu đề | đăng xuất |
| GET | `/api/authors?q=` | Đăng nhập | tìm tác giả theo tên hoặc OpenReview ID, nhiều bài lên trước |
| GET | `/api/meta` | cả 3 | danh sách venue, năm, lĩnh vực, decision (cho bộ lọc, form sở thích) |
| GET | `/api/papers?q=&venue=&year=&decision=&has_code=&offset=&limit=` | Bài báo | `q` rỗng: gợi ý theo hồ sơ (`mode=recommend`); có `q`: tìm theo từ khoá (`mode=search`) |
| GET | `/api/papers/{id}` | Đọc bài | chi tiết, review, các lần nộp |
| GET | `/api/papers/{id}/related?limit=` | Đọc bài | mục "Có thể bạn quan tâm" |
| POST | `/api/papers/{id}/pdf` | Đọc bài | tải PDF từ OpenReview về cache (`data/pdf_cache/`); 429 khi hết lượt |
| GET | `/api/papers/{id}/pdf` | Đọc bài | trả PDF đã cache để nhúng iframe; chưa cache thì 404 |
| GET / PUT | `/api/me` | Tài khoản | tên, email, sở thích; OpenReview ID chỉ đọc (cần đăng nhập, như mọi `/api/me...` và `/api/feedback`) |
| GET | `/api/me/authored` | Tài khoản | bài có `authorids` chứa OpenReview ID, kèm trạng thái xác nhận |
| PUT | `/api/me/authored/{id}` | Tài khoản | xác nhận / bỏ xác nhận "đây là bài của tôi" |
| GET | `/api/me/saved` | Tài khoản | bài đã lưu |
| POST | `/api/feedback` | Bài báo, Đọc bài | `saved`, `unsaved`, `relevant`, `not_relevant`, `already_read`, `clicked` |

Kiểu dữ liệu ở [schemas.py](schemas.py); frontend có bản sao ở `app/src/types.ts`, sửa một bên thì sửa cả bên kia.

## PDF

openreview.net không cho nhúng iframe (`X-Frame-Options: SAMEORIGIN`) và chặn tải ẩn danh, nên backend tải hộ
qua API có đăng nhập (cần `OPENREVIEW_USERNAME` / `PASSWORD` trong `.env`) rồi phục vụ từ cùng origin.
API của OpenReview chỉ cho **khoảng 26 PDF mỗi giờ**, nên PDF chỉ tải khi người dùng bấm "Xem PDF tại đây"
và được giữ lại mãi trong `data/pdf_cache/`. Bản demo lưu file trên ổ đĩa; khi triển khai có thể đổi sang
Redis / object storage trong [pdf.py](pdf.py) mà giữ nguyên interface.

## Gợi ý

- Đã đăng nhập và hồ sơ có bài (đã viết, đã lưu, đã đọc): [recsys/service.py](../recsys/service.py), mô hình tuyến tính B6
  đã học trong `eval`, chỉnh theo sở thích (độ mới, độ đa dạng, lĩnh vực, từ khoá; xem
  [recsys/README.md](../recsys/README.md)). Mỗi lần gợi ý ghi 100 bài đầu vào `rec_runs` / `rec_items`.
  Các sở thích này sửa được ngay ở cột trái trang danh sách, lưu vào cùng hồ sơ với trang Tài khoản.
- Chưa đăng nhập, hoặc hồ sơ còn trống (spec 7.4 tầng 3): [placeholder.py](placeholder.py), chất lượng q_p nhân độ mới,
  cộng điểm nếu khớp lĩnh vực / từ khoá trong sở thích khai báo.
- Bộ lọc (venue, năm, bài reject, có code) áp cho cả hai: bộ lọc trên trang gộp với sở thích, trùng tiêu chí thì
  bộ lọc trên trang thắng ([placeholder.py](placeholder.py) `recommend_filter`). Với recsys, bộ lọc áp ngay ở bước sinh ứng viên.
- Tìm kiếm: mọi từ phải có trong tiêu đề, abstract hoặc keywords.
- Bài liên quan: cosine SPECTER2.

Lý do gợi ý trả về dạng mã + tham số (`Reason` trong [schemas.py](schemas.py)); frontend dịch bằng khoá `reason.<mã>`.
