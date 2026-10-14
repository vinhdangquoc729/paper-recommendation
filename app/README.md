# Module app (frontend React)

React 18 + TypeScript + Vite, không dùng thư viện giao diện. Gọi backend qua `/api` (Vite chuyển tiếp sang
`http://127.0.0.1:8000` khi dev).

```bash
npm install
npm run dev        # http://localhost:5173, cần chạy song song: python -m api
npm run build      # kiểm tra kiểu + đóng gói ra dist/
```

## Ba màn hình

| Đường dẫn | Màn | Nội dung |
|---|---|---|
| `/` | Bài báo | Ô tìm kiếm. Để trống: danh sách gợi ý theo hồ sơ, có lý do "Vì sao gợi ý". Có từ khoá: kết quả tìm kiếm. Bộ lọc venue, năm, kết quả, có code. Nút Lưu / Liên quan / Không liên quan / Đã đọc trên từng bài. |
| `/paper/:id` | Đọc bài | Tiêu đề, tác giả, link OpenReview / code, TL;DR, tóm tắt, thông tin review, các lần nộp, PDF nhúng (tải khi bấm). Bên dưới: bảng "Có thể bạn quan tâm". |
| `/account` | Tài khoản | Thông tin cá nhân, OpenReview ID (tìm và xác nhận bài của mình), sở thích (lĩnh vực, venue, từ khoá, năm, bài bị reject, chỉ bài có code, độ mới, độ đa dạng), bài đã lưu. |

Rê chuột (hoặc Tab tới) tên bài ở bất kỳ đâu sẽ hiện khung xem nhanh: tác giả, hội nghị, kết quả, abstract cắt còn khoảng 600 ký tự.

Trạng thái tìm kiếm và bộ lọc nằm trên URL (`/?q=diffusion&venue=iclr&page=2`) nên nút Back và chia sẻ link hoạt động.

## Quy ước giao diện

- Cổ điển, ít trang trí: nền trắng, đường kẻ mảnh, bảng và `fieldset`; không bo góc, không đổ bóng, không dùng kiểu "thẻ".
- Màu chủ đạo là xanh lá Excel (`--green-700: #217346`, thanh tiêu đề `#185c37`), khai báo ở đầu [styles.css](src/styles.css).
- Tiêu đề bài dùng font có chân (Cambria / Times New Roman, có đủ dấu tiếng Việt); phần còn lại dùng Segoe UI.
- Không dùng ký tự gạch dài và dấu chấm giữa trong văn bản giao diện; ngăn cách bằng `|` hoặc dấu phẩy.

## Cấu trúc

```
src/
├── api.ts          # lớp gọi API duy nhất
├── types.ts        # khớp với api/schemas.py
├── format.ts       # nhãn decision, định dạng số / ngày kiểu Việt Nam
├── components/     # PaperRow, PaperLink (khung xem nhanh), PaperMeta, FeedbackBar, PdfViewer
└── pages/          # PapersPage, PaperPage, AccountPage
```
