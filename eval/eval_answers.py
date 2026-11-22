"""End-to-end evaluation: answer every question, then check the answer, the citations and the refusals.

  correct        an LLM judge compares the answer with the reference answer (facts must match)
  cited_right    at least one cited source is a gold article
  refused        the system said it could not find the answer
For unanswerable questions, refusing is the correct behaviour.

Usage: python eval/eval_answers.py      (needs an API key in .env; uses about 150k tokens)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bankrag.answer import answer  # noqa: E402
from bankrag.evaluate import is_relevant, load_questions  # noqa: E402
from bankrag.llm import PROVIDERS, ChatLLM, from_env  # noqa: E402
from bankrag.retrieve import load_retriever  # noqa: E402

JUDGE = """You grade answers to questions about banking regulation. Compare the system answer with the
reference answer. The system answer is correct if it states the same key facts (figures, deadlines,
yes/no, named texts) as the reference, in any language and wording. Extra correct detail is fine.
A refusal ("could not find") is incorrect. Reply with JSON only: {"correct": true|false, "reason": "..."}"""


def judge(llm, q: dict, system_answer: str) -> tuple[bool, str]:
    reply = llm.complete(JUDGE, f"Question: {q['question']}\nReference answer: {q['answer']}\n"
                                f"System answer: {system_answer}")
    try:
        data = json.loads(reply[reply.find("{"): reply.rfind("}") + 1])
        return bool(data.get("correct")), str(data.get("reason", ""))
    except json.JSONDecodeError:
        return False, "judge reply was not JSON: " + reply[:100]


def main() -> None:
    load_dotenv(ROOT / ".env")
    llm = from_env()
    base_url, key_var, _ = PROVIDERS["groq"]
    judge_llm = ChatLLM(base_url, os.getenv("BANKRAG_JUDGE_MODEL", "openai/gpt-oss-20b"), os.getenv(key_var))
    retriever = load_retriever(ROOT / "index")
    questions = load_questions(ROOT / "eval" / "questions.jsonl")

    # resumable: rows are saved as they are produced, and a re-run with the same models skips them,
    # so hitting a provider's daily quota halfway does not lose the work already done
    out_path = ROOT / "eval" / "answers.jsonl"
    done = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("model") == llm.model and r.get("judge") == judge_llm.model:
                done[r["id"]] = r
    out_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in done.values()), encoding="utf-8")

    rows = []
    for q in questions:
        if q["id"] in done:
            rows.append(done[q["id"]])
            continue
        t0 = time.time()
        out = answer(q["question"], retriever, llm)
        answerable = bool(q["gold"])
        rank = next((h["rank"] for h in out["retrieved"] if answerable and is_relevant(h, q["gold"])), None)
        row = {"id": q["id"], "lang": q["lang"], "answerable": answerable, "refused": out["refused"],
               "answer": out["answer"], "search_query": out["search_query"], "retrieval_rank": rank,
               "cited": [f"{s['circular']} {s['article']}" for s in out["sources"]],
               "cited_right": any(is_relevant(s, q["gold"]) for s in out["sources"]) if answerable else None,
               "seconds": round(time.time() - t0, 1)}
        if answerable and not out["refused"]:
            row["correct"], row["judge_reason"] = judge(judge_llm, q, out["answer"])
        else:
            row["correct"] = out["refused"] if not answerable else False
        row.update(model=llm.model, judge=judge_llm.model)
        rows.append(row)
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{q['id']}: {'OK ' if row['correct'] else 'BAD'} refused={row['refused']} "
              f"cited={row['cited']} {row['seconds']}s", flush=True)

    def pct(xs):
        return f"{100 * sum(xs) / len(xs):.0f}%" if xs else "–"

    ans = [r for r in rows if r["answerable"]]
    na = [r for r in rows if not r["answerable"]]
    md = ["# Answer evaluation", "",
          f"Answer model: `{llm.model}` · judge: `{judge_llm.model}` · retrieval: hybrid + rerank, "
          f"non-French questions translated to French for search · {time.strftime('%Y-%m-%d')}", "",
          "| Questions | n | Correct | Cites a right article | Refused | Right article in top 5 |",
          "|---|---|---|---|---|---|"]
    for lang in ("fr", "en", "ar"):
        rs = [r for r in ans if r["lang"] == lang]
        md.append(f"| Answerable ({lang}) | {len(rs)} | {pct([r['correct'] for r in rs])} | "
                  f"{pct([r['cited_right'] for r in rs])} | {pct([r['refused'] for r in rs])} | "
                  f"{pct([bool(r['retrieval_rank']) for r in rs])} |")
    md.append(f"| **Answerable (all)** | {len(ans)} | **{pct([r['correct'] for r in ans])}** | "
              f"{pct([r['cited_right'] for r in ans])} | {pct([r['refused'] for r in ans])} | "
              f"{pct([bool(r['retrieval_rank']) for r in ans])} |")
    md.append(f"| **Unanswerable** (should refuse) | {len(na)} | **{pct([r['correct'] for r in na])}** "
              f"refused correctly | – | {pct([r['refused'] for r in na])} | – |")
    wrong = [r for r in rows if not r["correct"]]
    if wrong:
        md += ["", "## Wrong or refused", "", "| Question | Answer given | Judge |", "|---|---|---|"]
        md += [f"| {r['id']} | {r['answer'][:160].replace('|', '/')} | {r.get('judge_reason', '')[:120]} |"
               for r in wrong]
    (ROOT / "eval" / "answers.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
