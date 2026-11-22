"""Four ways to find the right passages, so they can be compared on the same questions.

  bm25           keyword search: exact terms, numbers, article references
  dense          vector search: meaning, including across languages (Arabic question, French text)
  hybrid         both, merged with reciprocal rank fusion (RRF)
  hybrid_rerank  hybrid, then a cross-encoder re-scores the top candidates against the question
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .ingest import Chunk, load
from .text import tokenize

EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3-int8"
MODES = ("bm25", "dense", "hybrid", "hybrid_rerank")


def passage(c: Chunk) -> str:
    """What the models see for a chunk: the circular's subject gives context to short articles."""
    return f"{c.title} — {c.article}: {c.text}" if c.article else f"{c.title}: {c.text}"


def rrf(rankings: list[list[int]], k: int = 60) -> list[int]:
    """Reciprocal rank fusion: an item ranked high in either list ends up high overall.

    k=60 is the value from the original paper (Cormack et al., 2009); it damps the weight of
    the very top ranks so one list cannot dominate.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)


class Retriever:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray, model_dir: str = "models"):
        self.chunks, self.vectors, self.model_dir = chunks, vectors, model_dir
        self.bm25 = BM25Okapi([tokenize(passage(c)) for c in chunks])
        self._embedder = self._reranker = None

    # models are loaded on first use, so keyword-only use (and the tests) stay fast
    @property
    def embedder(self):
        if self._embedder is None:
            from fastembed import TextEmbedding
            self._embedder = TextEmbedding(EMBED_MODEL, cache_dir=self.model_dir)
        return self._embedder

    @property
    def reranker(self):
        if self._reranker is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            self._reranker = TextCrossEncoder(RERANK_MODEL, cache_dir=self.model_dir)
        return self._reranker

    def rank_bm25(self, query: str, n: int) -> list[int]:
        scores = self.bm25.get_scores(tokenize(query))
        return [int(i) for i in np.argsort(-scores)[:n] if scores[i] > 0]

    def rank_dense(self, query: str, n: int) -> list[int]:
        q = np.array(next(iter(self.embedder.embed([query]))))
        sims = self.vectors @ (q / np.linalg.norm(q))
        return [int(i) for i in np.argsort(-sims)[:n]]

    def search(self, query: str, mode: str = "hybrid_rerank", k: int = 5, candidates: int = 30) -> list[dict]:
        if mode == "bm25":
            order = self.rank_bm25(query, k)
        elif mode == "dense":
            order = self.rank_dense(query, k)
        else:
            order = rrf([self.rank_bm25(query, candidates), self.rank_dense(query, candidates)])[:candidates]
            if mode == "hybrid_rerank":
                scores = list(self.reranker.rerank(query, [passage(self.chunks[i]) for i in order]))
                order = [i for _, i in sorted(zip(scores, order), key=lambda x: -x[0])]
            order = order[:k]
        return [{**asdict(self.chunks[i]), "rank": r + 1} for r, i in enumerate(order)]


def build_index(chunks: list[Chunk], out: Path, model_dir: str = "models") -> None:
    from fastembed import TextEmbedding
    embedder = TextEmbedding(EMBED_MODEL, cache_dir=model_dir)
    vectors = np.array(list(embedder.embed([passage(c) for c in chunks], batch_size=32)), dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "vectors.npy", vectors)
    (out / "meta.json").write_text(json.dumps({"embed_model": EMBED_MODEL, "chunks": len(chunks)}), encoding="utf-8")


def load_retriever(index_dir: Path, model_dir: str = "models") -> Retriever:
    return Retriever(load(index_dir / "chunks.jsonl"), np.load(index_dir / "vectors.npy"), model_dir)
