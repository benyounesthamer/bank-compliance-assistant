"""Measure retrieval: does the right article come back, and how high?

A retrieved chunk is correct when it belongs to a gold circular and, if the question names
articles, to one of those articles. French and Arabic versions of the same circular share a
number, so either language counts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ORDINALS = {"premier": 1, "1er": 1, "الأول": 1, "الأوّل": 1, "الثاني": 2, "الثالث": 3, "الرابع": 4, "الخامس": 5}


def article_number(label: str) -> int | None:
    if m := re.search(r"\d+", label):
        return int(m.group())
    for word, n in ORDINALS.items():
        if word in label.lower():
            return n
    return None


def is_relevant(hit: dict, gold: list[dict]) -> bool:
    for g in gold:
        if hit["circular"] == g["circular"]:
            if not g["articles"] or article_number(hit["article"]) in g["articles"]:
                return True
    return False


def load_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def score_retrieval(retriever, questions: list[dict], mode: str, k: int = 10, search=None) -> dict:
    """hit@1, hit@5 and MRR@10, overall and per question language. `search` lets a caller
    transform the query first (e.g. translate it) while keeping the scoring identical."""
    rows = []
    for q in questions:
        if not q["gold"]:
            continue  # unanswerable questions are scored on the answer side
        hits = search(q["question"], mode, k) if search else retriever.search(q["question"], mode, k=k)
        rank = next((h["rank"] for h in hits if is_relevant(h, q["gold"])), None)
        rows.append({"id": q["id"], "lang": q["lang"], "rank": rank})

    def summary(rs):
        n = len(rs) or 1
        return {"n": len(rs),
                "hit@1": sum(r["rank"] == 1 for r in rs) / n,
                "hit@5": sum(r["rank"] is not None and r["rank"] <= 5 for r in rs) / n,
                "mrr@10": sum(1 / r["rank"] for r in rs if r["rank"]) / n}

    langs = sorted({r["lang"] for r in rows})
    return {"all": summary(rows), **{lang: summary([r for r in rows if r["lang"] == lang]) for lang in langs},
            "misses": [r["id"] for r in rows if r["rank"] is None or r["rank"] > 5]}
