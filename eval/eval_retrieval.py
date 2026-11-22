"""Compare the four search modes on the evaluation questions. No API key needed.

Usage: python eval/eval_retrieval.py       (about 10 minutes on a laptop CPU, mostly the reranker)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bankrag.evaluate import load_questions, score_retrieval  # noqa: E402
from bankrag.retrieve import EMBED_MODEL, MODES, RERANK_MODEL, load_retriever  # noqa: E402

NAMES = {"bm25": "Keywords (BM25)", "dense": "Vectors", "hybrid": "Keywords + vectors (RRF)",
         "hybrid_rerank": "Keywords + vectors + reranker"}


def main() -> None:
    retriever = load_retriever(ROOT / "index")
    questions = load_questions(ROOT / "eval" / "questions.jsonl")
    results, timing = {}, {}
    for mode in MODES:
        t0 = time.time()
        results[mode] = score_retrieval(retriever, questions, mode)
        timing[mode] = (time.time() - t0) / results[mode]["all"]["n"]
        print(mode, results[mode]["all"], flush=True)

    (ROOT / "eval" / "retrieval.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    n = results["bm25"]["all"]["n"]
    md = ["# Retrieval evaluation", "",
          f"{n} answerable questions (French, English, Arabic) · embeddings `{EMBED_MODEL}` · "
          f"reranker `{RERANK_MODEL}` · questions searched as written (no translation) · {time.strftime('%Y-%m-%d')}", "",
          "**hit@1**: the right article is the first result. **hit@5**: it is in the top 5. "
          "**MRR@10**: mean of 1/rank of the first right article.", "",
          "| Mode | hit@1 | hit@5 | MRR@10 | hit@1 FR | hit@1 EN | hit@1 AR | Time per query |",
          "|---|---|---|---|---|---|---|---|"]
    for mode in MODES:
        r = results[mode]
        md.append(f"| {NAMES[mode]} | {r['all']['hit@1']:.0%} | {r['all']['hit@5']:.0%} | {r['all']['mrr@10']:.2f} | "
                  f"{r['fr']['hit@1']:.0%} | {r['en']['hit@1']:.0%} | {r['ar']['hit@1']:.0%} | {timing[mode]:.1f}s |")
    md += ["", "Missed in the top 5 with the best mode: " + (", ".join(results["hybrid_rerank"]["misses"]) or "none")]
    (ROOT / "eval" / "retrieval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
