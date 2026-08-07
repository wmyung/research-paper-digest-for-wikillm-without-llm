from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")


def tokenize(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)]


def chunk_markdown(markdown: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_h2 = "Frontmatter"
    current_h3 = ""
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        if text and len(tokenize(text)) >= 8:
            label = current_h2 + (" / " + current_h3 if current_h3 else "")
            chunks.append((label, text))
        buffer = []

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            current_h2 = line[3:].strip()
            current_h3 = ""
        elif line.startswith("### "):
            flush()
            current_h3 = line[4:].strip()
        elif not line.strip():
            flush()
        else:
            buffer.append(line)
    flush()
    return chunks


@dataclass(slots=True)
class RetrievalHit:
    rank: int
    label: str
    score: float
    text: str


class BM25Index:
    def __init__(self, chunks: list[tuple[str, str]], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        self.docs = [tokenize(label + " " + text) for label, text in chunks]
        self.lengths = [len(doc) for doc in self.docs]
        self.avgdl = sum(self.lengths) / max(1, len(self.lengths))
        self.tf = [Counter(doc) for doc in self.docs]
        self.df: Counter[str] = Counter()
        for doc in self.docs:
            self.df.update(set(doc))

    def search(self, query: str, top_k: int = 10) -> list[RetrievalHit]:
        terms = tokenize(query)
        n = len(self.docs)
        scored: list[tuple[float, int]] = []
        for i, frequencies in enumerate(self.tf):
            score = 0.0
            dl = self.lengths[i]
            for term in terms:
                f = frequencies.get(term, 0)
                if not f:
                    continue
                df = self.df[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                denom = f + self.k1 * (1 - self.b + self.b * dl / max(1.0, self.avgdl))
                score += idf * f * (self.k1 + 1) / denom
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [
            RetrievalHit(rank=rank, label=self.chunks[index][0], score=round(score, 6), text=self.chunks[index][1])
            for rank, (score, index) in enumerate(scored[:top_k], start=1)
        ]


def run_queries(markdown: str, queries: Iterable[dict], top_k: int = 10) -> dict:
    index = BM25Index(chunk_markdown(markdown))
    results: list[dict] = []
    passed = 0
    for item in queries:
        query = str(item.get("query") or item.get("q") or "").strip()
        expected = [str(value).casefold() for value in item.get("expected_terms", item.get("must_contain", []))]
        hits = index.search(query, top_k=top_k)
        rank = None
        for hit in hits:
            haystack = (hit.label + " " + hit.text).casefold()
            if not expected or all(term in haystack for term in expected):
                rank = hit.rank
                break
        ok = rank is not None
        passed += int(ok)
        results.append(
            {
                "id": item.get("id"),
                "query": query,
                "expected_terms": expected,
                "passed": ok,
                "first_matching_rank": rank,
                "hits": [asdict(hit) for hit in hits],
            }
        )
    return {"passed": passed, "total": len(results), "top_k": top_k, "results": results}
