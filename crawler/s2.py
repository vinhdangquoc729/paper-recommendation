"""Cào Semantic Scholar Graph API.

Ba bước, mỗi bước ghi cache thô vào data/raw/s2/ và có thể chạy lại (resume):
1. papers    : bulk search theo venue -> metadata bài (title, abstract, tác giả, citation...)
2. references: batch API -> danh sách reference của từng bài
3. edges     : endpoint /references của một mẫu bài -> intents, isInfluential, contexts
"""
import logging
import os
import random

from common.config import RAW_DIR
from common.http import ApiClient
from common.jsonl import append_jsonl, read_jsonl, write_jsonl_atomic
from crawler.venues import Venue

log = logging.getLogger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"
S2_DIR = RAW_DIR / "s2"
REFS_PATH = S2_DIR / "references.jsonl"
EDGES_PATH = S2_DIR / "edges_sample.jsonl"

PAPER_FIELDS = ",".join([
    "title", "abstract", "year", "publicationDate", "venue", "externalIds", "authors",
    "citationCount", "influentialCitationCount", "referenceCount", "openAccessPdf",
])


def papers_path(venue_key: str):
    return S2_DIR / f"papers_{venue_key}.jsonl"


def make_client() -> ApiClient:
    key = os.environ.get("S2_API_KEY")
    if not key:
        log.warning("Chưa có S2_API_KEY: dùng pool ẩn danh, sẽ chậm và hay bị 429")
    return ApiClient(
        S2_BASE,
        min_interval=1.05 if key else 1.5,
        headers={"x-api-key": key} if key else None,
        max_retries=12,
        max_retry_after=None,   # crawler chạy nền: server bắt chờ bao lâu thì chờ bấy lâu
    )


def crawl_venue_papers(client: ApiClient, venue: Venue) -> int:
    # Năm trên S2 thường là năm lên arXiv, có thể sớm hơn năm hội nghị một năm.
    # Năm hội nghị thật được suy ra từ DBLP key lúc load.
    years = f"{min(venue.editions) - 1}-{max(venue.editions)}"
    records, token = [], None
    while True:
        params = {"query": "", "venue": venue.s2_name, "year": years, "fields": PAPER_FIELDS}
        if token:
            params["token"] = token
        data = client.request("GET", "paper/search/bulk", params=params)
        records.extend(data.get("data") or [])
        log.info("[s2-papers] %s: %d / %s", venue.key, len(records), data.get("total"))
        token = data.get("token")
        if not token:
            break
    return write_jsonl_atomic(papers_path(venue.key), records)


def crawl_references(client: ApiClient, paper_ids: list[str], batch_size: int = 100) -> int:
    done = {r["paperId"] for r in read_jsonl(REFS_PATH)}
    todo = [p for p in dict.fromkeys(paper_ids) if p not in done]
    log.info("[s2-refs] %d bài đã có, còn %d bài", len(done), len(todo))
    for i in range(0, len(todo), batch_size):
        chunk = todo[i:i + batch_size]
        data = client.request(
            "POST", "paper/batch",
            params={"fields": "referenceCount,references.paperId,references.year"},
            json={"ids": chunk},
        )
        out = []
        for pid, item in zip(chunk, data):
            refs = (item or {}).get("references") or []
            out.append({
                "paperId": pid,
                "found": item is not None,
                "referenceCount": (item or {}).get("referenceCount"),
                "references": [[r.get("paperId"), r.get("year")] for r in refs],
            })
        append_jsonl(REFS_PATH, out)
        log.info("[s2-refs] %d / %d", min(i + batch_size, len(todo)), len(todo))
    return len(todo)


def crawl_edges_sample(client: ApiClient, paper_ids: list[str], n: int, seed: int = 0) -> int:
    """Lấy đặc trưng cạnh (intents, isInfluential, contexts) cho một mẫu ngẫu nhiên.

    Endpoint này phải gọi từng bài nên không cào toàn bộ; mẫu đủ để ước lượng độ phủ
    và làm nguồn cho bước gán nhãn tay cạnh trích dẫn (V3).
    """
    done = {r["paperId"] for r in read_jsonl(EDGES_PATH)}
    pool = sorted(set(paper_ids) - done)
    random.Random(seed).shuffle(pool)
    todo = pool[:max(0, n - len(done))]
    log.info("[s2-edges] đã có %d, lấy thêm %d", len(done), len(todo))
    for k, pid in enumerate(todo, 1):
        data = client.request(
            "GET", f"paper/{pid}/references",
            params={"fields": "paperId,year,intents,isInfluential,contexts", "limit": 1000},
        )
        edges = [
            {
                "cited": (e.get("citedPaper") or {}).get("paperId"),
                "isInfluential": e.get("isInfluential"),
                "intents": e.get("intents") or [],
                "contexts": e.get("contexts") or [],
            }
            for e in (data.get("data") or [])
        ]
        append_jsonl(EDGES_PATH, [{"paperId": pid, "elided": data.get("data") is None, "edges": edges}])
        if k % 25 == 0:
            log.info("[s2-edges] %d / %d", k, len(todo))
    return len(todo)
