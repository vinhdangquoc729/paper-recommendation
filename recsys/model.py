"""Mô hình xếp hạng tuyến tính đã học (eval.ablation xuất ra data/models/), dùng ở sản phẩm.

score = Σ_j w_j · z_j, z là đặc trưng đã chuẩn hoá trong danh sách ứng viên (recsys.ranking). Thành phần w_j · z_j
của từng đặc trưng cũng là cơ sở cho lời giải thích "vì sao gợi ý".
"""
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from common.config import DATA_DIR

MODELS_DIR = DATA_DIR / "models"
DEFAULT_MODEL = MODELS_DIR / "linear_b6.json"


@dataclass
class LinearModel:
    name: str
    features: list[str]
    weights: list[float]
    info: dict = field(default_factory=dict)   # dữ liệu huấn luyện, độ đo trên val

    @property
    def w(self) -> np.ndarray:
        return np.asarray(self.weights, dtype=np.float32)

    def modes(self) -> tuple[str, ...]:
        """Các chế độ trọng số cạnh mà đặc trưng của mô hình cần (rel_w, cocit_w... -> 'w')."""
        found = {f.split("_", 1)[1] for f in self.features if f.startswith(("rel_", "cocit_", "coupling_"))}
        return tuple(sorted(found - {"mean"}))

    def save(self, path: Path = DEFAULT_MODEL) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = DEFAULT_MODEL) -> "LinearModel":
        return cls(**json.loads(path.read_text(encoding="utf-8")))
