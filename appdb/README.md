# Module appdb: CSDL của sản phẩm (Postgres + pgvector)

```
data/ (crawler + features) ──► python -m appdb sync ──► Postgres ◄──► api (đọc catalog, ghi dữ liệu người dùng)
```

Chạy trong Docker (`docker compose up -d db`), cổng **55432** trên máy (5432 và 5433 thường đã có Postgres cài sẵn).
Chuỗi kết nối: biến `DATABASE_URL`, mặc định `postgresql://paperrec:paperrec@localhost:55432/paperrec`.

| Lệnh | Làm gì |
|---|---|
| `migrate` | áp các file [migrations/](migrations/) chưa chạy (theo thứ tự tên, ghi vào `schema_migrations`) |
| `sync` | nạp catalog từ `data/` và tạo sẵn tài khoản cho tác giả mới (khoảng 40 giây) |
| `import-legacy` | chuyển hồ sơ / phản hồi của bản demo một người dùng cũ (`data/app.sqlite`) |
| `status` | số dòng các bảng chính |

Thứ tự khi có dữ liệu mới: `python -m crawler load` → `python -m features all` → `python -m appdb sync`.
API đang chạy tự nạp lại catalog khi `catalog_meta.version` đổi (kiểm tra mỗi phút).

## Lược đồ ([001_init.sql](migrations/001_init.sql))

**Catalog**: chỉ `sync` ghi, thay cả lô trong một transaction.

| Bảng | Nội dung |
|---|---|
| `papers` | mỗi bài một dòng (item của features, đã gộp lần nộp lại): metadata, q_p, embedding SPECTER2 `vector(768)` |
| `paper_versions` | mọi lần nộp trên OpenReview → bài |
| `authors`, `paper_authors` | tác giả có OpenReview ID; `authors` chỉ thêm, không xoá (`users` trỏ tới) |
| `citations`, `papers_with_refs` | cạnh trích dẫn giữa hai bài trong corpus kèm ngữ cảnh trích; trọng số w tính lúc nạp vào bộ nhớ |
| `reviews` | điểm review gốc |
| `catalog_meta` | phiên bản catalog (thời điểm sync) |

**Người dùng**: API ghi. Không có khoá ngoại tới `papers` vì catalog được thay cả lô; `sync` ánh xạ lại `paper_id` cũ
qua `paper_versions` khi bài được gộp khác đi.

| Bảng | Nội dung |
|---|---|
| `users` | mỗi tác giả một tài khoản `seeded` tạo sẵn (`author_id`); người chưa có bài đăng ký bằng email (`author_id` NULL). Mật khẩu băm scrypt |
| `sessions` | phiên đăng nhập (cookie), 30 ngày |
| `user_papers` | trạng thái hiện tại: `saved`, `read`, và phần sửa của người dùng với `authored` (bỏ xác nhận, tự thêm) |
| `events` | nhật ký thao tác, chỉ ghi thêm: lưu, liên quan / không liên quan, đã đọc, mở PDF |
| `rec_runs`, `rec_items` | mỗi lần gợi ý: 100 bài đầu, điểm, đóng góp từng đặc trưng (để giải thích và đo online) |

Bài mà `authors` có ít hơn số tác giả đếm thô trong `or_submissions` là vì `sync` lấy danh sách tác giả
dài nhất trong các lần nộp lại của một bài, giống `recsys.snapshot`.
