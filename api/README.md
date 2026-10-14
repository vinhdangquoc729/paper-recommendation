# Module api (backend FastAPI)

```
data/features/ (items, quality, embedding)  ─┐
data/corpus.sqlite (review gốc)              ├─► python -m api ─► http://127.0.0.1:8000/api/...
data/app.sqlite (hồ sơ, phản hồi)           ─┘
```

Chỉ **đọc** đầu ra của `features/`; trạng thái người dùng ghi vào `data/app.sqlite`.
Hiện chỉ có một người dùng, chưa đăng nhập. Tài liệu tương tác: http://127.0.0.1:8000/docs.

| Method | Đường dẫn | Dùng ở màn | Mô tả |
|---|---|---|---|
| GET | `/api/meta` | cả 3 | danh sách venue, năm, lĩnh vực, decision (cho bộ lọc, form sở thích) |
| GET | `/api/papers?q=&venue=&year=&decision=&has_code=&offset=&limit=` | Bài báo | `q` rỗng: gợi ý theo hồ sơ (`mode=recommend`); có `q`: tìm theo từ khoá (`mode=search`) |
| GET | `/api/papers/{id}` | Đọc bài | chi tiết, review, các lần nộp |
| GET | `/api/papers/{id}/related?limit=` | Đọc bài | mục "Có thể bạn quan tâm" |
| POST | `/api/papers/{id}/pdf` | Đọc bài | tải PDF từ OpenReview về cache (`data/pdf_cache/`); 429 khi hết lượt |
| GET | `/api/papers/{id}/pdf` | Đọc bài | trả PDF đã cache để nhúng iframe; chưa cache thì 404 |
| GET / PUT | `/api/me` | Tài khoản | tên, email, OpenReview ID, sở thích |
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

## Logic gợi ý tạm thời

[placeholder.py](placeholder.py) chỉ để giao diện có dữ liệu thật, **chưa phải thuật toán của đề tài**:

- Gợi ý: chất lượng q_p nhân độ mới, cộng điểm nếu khớp lĩnh vực / từ khoá trong sở thích; loại bài đã đánh dấu
  "Không liên quan", "Đã đọc" và bài của chính người dùng.
- Tìm kiếm: mọi từ phải có trong tiêu đề, abstract hoặc keywords.
- Bài liên quan: cosine SPECTER2 nếu đã chạy `python -m features embed`, nếu chưa thì bài cùng lĩnh vực.

Khi có module `recsys/`, thay các hàm trong file này, giữ nguyên chữ ký.
