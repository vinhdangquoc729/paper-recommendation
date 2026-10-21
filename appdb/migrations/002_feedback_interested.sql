-- Nút phản hồi mới: Lưu / Quan tâm / Không quan tâm; "đã đọc" suy từ việc mở trang bài (Preferences.auto_read).
-- Đổi tên phản hồi cũ cho khớp; "already_read" giữ nguyên trong nhật ký (đã có dòng role = 'read' trong user_papers).
UPDATE events SET type = 'interested' WHERE type = 'relevant';
UPDATE events SET type = 'not_interested' WHERE type = 'not_relevant';
