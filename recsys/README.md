# Module recsys: lõi gợi ý (spec Khối 1-6)

Dùng chung cho sản phẩm (`api`, qua [service.py](service.py)) và đánh giá (`eval`): cùng một đoạn code chạy cho
"tác giả tại mốc T trong quá khứ" và "người dùng hôm nay".

| File | Nội dung |
|---|---|
| [snapshot.py](snapshot.py) | `World` (dữ liệu tại mốc T: pool, đồ thị trích dẫn, độ phổ biến), `Case` (một người dùng), `build_world` |
| [profile.py](profile.py) | trọng số hồ sơ (spec 7.2), hồ sơ một vector, hồ sơ đa sở thích (spherical k-means có trọng số) |
| [graph.py](graph.py) | co-citation, coupling cho cả hồ sơ bằng nhân ma trận thưa |
| [pipeline.py](pipeline.py) | sinh ứng viên (hợp top bài theo từng nguồn) và đặc trưng; trọng số cạnh theo [features/reference_filter.py](../features/reference_filter.py) |
| [ranking.py](ranking.py) | chuẩn hoá đặc trưng trong danh sách ứng viên, điểm tuyến tính |
| [model.py](model.py) | mô hình tuyến tính đã học (`data/models/linear_b6.json`, do `python -m eval ablation` xuất ra) |
| [rerank.py](rerank.py) | MMR |
| [service.py](service.py) | `Recommender`: hồ sơ từ bài đã viết / trích / lưu / đọc, gợi ý, lý do |

## Gợi ý cho người dùng thật ([service.py](service.py))

1. `World` tại T = ngày mai từ catalog trong Postgres; chỉ tính các chế độ trọng số cạnh mà mô hình dùng.
2. Hồ sơ: bài có OpenReview ID của người dùng (trừ bài họ bỏ xác nhận, cộng bài tự thêm), các bài đó trích (0,5 · w),
   bài đã lưu (0,7), đã đọc (0,3), nhân time decay 3 năm.
3. Loại: bài đã viết, đã trích, đã lưu / đọc, bị đánh "không liên quan", và bài không phải ứng viên (withdrawn, desk-reject,
   đang review).
4. Ứng viên + đặc trưng → điểm tuyến tính chỉnh theo sở thích khai báo (`Tuning`) → MMR theo thanh "Độ đa dạng"
   (λ = 1 − 0,5 · đa dạng). Sở thích:
   - "Độ mới" f ∈ [0, 1]: trọng số `age` nhân 2f, `pop` nhân 1,5 − f (f = 0,5 giữ nguyên trọng số đã học);
   - bài thuộc lĩnh vực quan tâm / khớp từ khoá được cộng 1 độ lệch chuẩn của điểm trong danh sách ứng viên
     (`AREA_BONUS_SD`, `KEYWORD_BONUS_SD`); lý do "khớp lĩnh vực / từ khoá" luôn hiện trước;
   - bài thuộc lĩnh vực / khớp từ khoá còn là một nguồn ứng viên riêng (`pref`, 100 bài gần nội dung hồ sơ nhất);
   - bộ lọc cứng (venue, năm, quyết định, có code; bộ lọc trên trang thắng sở thích khi trùng tiêu chí) do API truyền
     vào `allowed`: mọi nguồn chỉ lấy ứng viên trong các bài thoả, nên lọc chặt vẫn đủ ứng viên.
5. Lý do: 2 đặc trưng đóng góp dương nhiều nhất (w_j · z_j), kèm tên bài gần nhất trong hồ sơ khi lý do là nội dung.

Hồ sơ trống (chưa có bài nào) trả về `None`: API gợi ý theo sở thích khai báo ([api/placeholder.py](../api/placeholder.py)).

Mỗi lượt gợi ý khoảng 0,4-0,6 giây; khởi động (nạp catalog, dựng đồ thị) khoảng 6-20 giây.

Đổi mô hình: chạy `python -m eval ablation --objective graded` (ghi `data/models/linear_b6_graded.json`), chép thành
`data/models/linear_b6.json`, khởi động lại API.
