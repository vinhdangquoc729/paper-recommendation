"""Embedding nội dung SPECTER2 (spec mục 6.1).

Mô hình allenai/specter2_base + adapter `proximity` (chính là embedding `specter_v2` của Semantic Scholar),
đầu vào `title [SEP] abstract`, lấy vector [CLS], chuẩn hoá L2 để cosine = tích vô hướng.
torch / transformers / adapters chỉ được import khi chạy lệnh embed.
"""
import logging
import time

import numpy as np

from common.config import FEATURES_DIR

log = logging.getLogger(__name__)

BASE_MODEL = "allenai/specter2_base"
ADAPTER = "allenai/specter2"
EMB_PATH = FEATURES_DIR / "specter2.npy"
IDS_PATH = FEATURES_DIR / "specter2_ids.txt"


def embed_texts(titles: list[str], abstracts: list[str], batch_size: int = 32, max_length: int = 512,
                device: str | None = None) -> np.ndarray:
    import torch
    from adapters import AutoAdapterModel
    from transformers import AutoTokenizer

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoAdapterModel.from_pretrained(BASE_MODEL)
    model.load_adapter(ADAPTER, source="hf", load_as="proximity", set_active=True)
    model.to(device).eval()
    if device == "cuda":
        model.half()
    log.info("[embed] %d bài trên %s", len(titles), device)

    texts = [(t or "") + tok.sep_token + (a or "") for t, a in zip(titles, abstracts)]
    order = np.argsort([len(t) for t in texts])   # gom bài dài ngắn giống nhau vào một batch, đỡ padding
    out = np.zeros((len(texts), model.config.hidden_size), dtype=np.float32)
    start = time.monotonic()
    with torch.inference_mode():
        for b, s in enumerate(range(0, len(texts), batch_size)):
            idx = order[s:s + batch_size]
            enc = tok([texts[i] for i in idx], padding=True, truncation=True, max_length=max_length,
                      return_tensors="pt", return_token_type_ids=False).to(device)
            out[idx] = model(**enc).last_hidden_state[:, 0, :].float().cpu().numpy()
            if b % 200 == 0:
                done = s + len(idx)
                rate = done / max(time.monotonic() - start, 1e-6)
                log.info("[embed] %d/%d (%.0f bài/s, còn ~%.0f phút)", done, len(texts), rate,
                         (len(texts) - done) / rate / 60)
    out /= np.linalg.norm(out, axis=1, keepdims=True).clip(min=1e-12)
    return out


def save(ids: list[str], emb: np.ndarray) -> None:
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    np.save(EMB_PATH, emb)
    IDS_PATH.write_text("\n".join(ids), encoding="utf-8")


def load() -> tuple[list[str], np.ndarray]:
    return IDS_PATH.read_text(encoding="utf-8").split("\n"), np.load(EMB_PATH)
