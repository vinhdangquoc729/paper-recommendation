"""Danh sách venue trong phạm vi corpus và cách tra chúng trên từng nguồn."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OpenReviewSource:
    venue_id: str          # ví dụ "ICLR.cc/2024/Conference"
    api: int               # 1 = api.openreview.net, 2 = api2.openreview.net
    invitation: str        # invitation của submission


@dataclass(frozen=True)
class Venue:
    key: str               # khoá ngắn dùng trong DB: iclr / neurips / tmlr
    s2_name: str           # tên venue trên Semantic Scholar (tham số `venue` của bulk search)
    dblp_prefix: str       # tiền tố DBLP key, dùng để suy ra năm hội nghị
    editions: tuple[int, ...]
    default_month: int     # tháng diễn ra hội nghị, dùng khi thiếu ngày công bố
    openreview: dict[int, OpenReviewSource]  # edition -> nguồn; TMLR dùng edition 0 = toàn bộ


VENUES: dict[str, Venue] = {
    "iclr": Venue(
        key="iclr",
        s2_name="International Conference on Learning Representations",
        dblp_prefix="conf/iclr/",
        editions=(2023, 2024, 2025, 2026),
        default_month=5,
        openreview={
            # ICLR 2023 vẫn nằm trên API v1
            2023: OpenReviewSource("ICLR.cc/2023/Conference", 1, "ICLR.cc/2023/Conference/-/Blind_Submission"),
            2024: OpenReviewSource("ICLR.cc/2024/Conference", 2, "ICLR.cc/2024/Conference/-/Submission"),
            2025: OpenReviewSource("ICLR.cc/2025/Conference", 2, "ICLR.cc/2025/Conference/-/Submission"),
            2026: OpenReviewSource("ICLR.cc/2026/Conference", 2, "ICLR.cc/2026/Conference/-/Submission"),
        },
    ),
    "neurips": Venue(
        key="neurips",
        s2_name="Neural Information Processing Systems",
        dblp_prefix="conf/nips/",
        editions=(2023, 2024, 2025),
        default_month=12,
        openreview={
            2023: OpenReviewSource("NeurIPS.cc/2023/Conference", 2, "NeurIPS.cc/2023/Conference/-/Submission"),
            2024: OpenReviewSource("NeurIPS.cc/2024/Conference", 2, "NeurIPS.cc/2024/Conference/-/Submission"),
            2025: OpenReviewSource("NeurIPS.cc/2025/Conference", 2, "NeurIPS.cc/2025/Conference/-/Submission"),
        },
    ),
    "icml": Venue(
        key="icml",
        s2_name="International Conference on Machine Learning",
        dblp_prefix="conf/icml/",
        editions=(2023, 2024, 2025, 2026),
        default_month=7,
        # Đã kiểm tra 10/2026: cả 4 năm đều ở API v2, chỉ công khai bài accept.
        # 2023-2024 không có review; 2025+ có review (điểm ở trường overall_recommendation).
        openreview={
            2023: OpenReviewSource("ICML.cc/2023/Conference", 2, "ICML.cc/2023/Conference/-/Submission"),
            2024: OpenReviewSource("ICML.cc/2024/Conference", 2, "ICML.cc/2024/Conference/-/Submission"),
            2025: OpenReviewSource("ICML.cc/2025/Conference", 2, "ICML.cc/2025/Conference/-/Submission"),
            2026: OpenReviewSource("ICML.cc/2026/Conference", 2, "ICML.cc/2026/Conference/-/Submission"),
        },
    ),
    "tmlr": Venue(
        key="tmlr",
        s2_name="Trans. Mach. Learn. Res.",
        dblp_prefix="journals/tmlr/",
        editions=(2023, 2024, 2025, 2026),
        default_month=6,
        openreview={0: OpenReviewSource("TMLR", 2, "TMLR/-/Submission")},
    ),
}
