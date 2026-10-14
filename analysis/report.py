"""Gom kết quả phân tích thành báo cáo Markdown + file JSON số liệu."""
import json
from pathlib import Path

import pandas as pd


def pct(x: float) -> str:
    return "n/a" if pd.isna(x) else f"{100 * x:.1f}%"


class Report:
    def __init__(self, title: str):
        self.parts = [f"# {title}\n"]
        self.stats: dict = {}

    def h2(self, text: str) -> None:
        self.parts.append(f"\n## {text}\n")

    def h3(self, text: str) -> None:
        self.parts.append(f"\n### {text}\n")

    def text(self, text: str) -> None:
        self.parts.append(text + "\n")

    def bullets(self, items: dict) -> None:
        self.parts.append("\n".join(f"- {k}: **{v}**" for k, v in items.items()) + "\n")

    def table(self, df: pd.DataFrame) -> None:
        self.parts.append(df.to_markdown(index=False, floatfmt=".2f") + "\n")

    def stat(self, key: str, value) -> None:
        if hasattr(value, "item"):
            value = value.item()
        self.stats[key] = value

    def save(self, md_path: Path, json_path: Path) -> None:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text("\n".join(self.parts), encoding="utf-8")
        json_path.write_text(json.dumps(self.stats, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
