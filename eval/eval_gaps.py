"""Evaluate the compliance gap analysis on test policies with known gaps.

  gap        any obligation that is not "met" (missing, partial or contradicts)
  recall     share of real gaps the checker flags as gaps
  false gaps share of compliant obligations the checker wrongly flags (needs_review counts as flagged)
  exact      share of obligations given exactly the expected status

Resumable: each policy's findings are saved in eval/gaps/; a re-run skips policies already done
with the same model.

Usage: python eval/eval_gaps.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bankrag.gaps import check_policy, summary  # noqa: E402
from bankrag.llm import from_env  # noqa: E402
from bankrag.obligations import load_obligations  # noqa: E402

POLICIES = ROOT / "eval" / "policies"
OUT = ROOT / "eval" / "gaps"


def main() -> None:
    load_dotenv(ROOT / ".env")
    llm = from_env()
    obligations = load_obligations(ROOT / "data" / "obligations" / "2022-08.json")
    labels = {k: v for k, v in json.loads((POLICIES / "labels.json").read_text(encoding="utf-8")).items()
              if not k.startswith("_")}
    OUT.mkdir(exist_ok=True)

    rows = []
    for name, exceptions in labels.items():
        out = OUT / (Path(name).stem + ".json")
        saved = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
        if not saved or saved.get("model") != llm.model:
            t0, calls = time.time(), llm.calls
            findings = check_policy((POLICIES / name).read_text(encoding="utf-8"), obligations, llm)
            saved = {"policy": name, "model": llm.model, "findings": findings, "seconds": round(time.time() - t0),
                     "llm_calls": llm.calls - calls, "truncated_replies": llm.truncated}
            out.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
        expected = {o["id"]: exceptions.get(o["id"], "met") for o in obligations}
        got = {f["id"]: f["status"] for f in saved["findings"]}
        real_gaps = [i for i, s in expected.items() if s != "met"]
        compliant = [i for i, s in expected.items() if s == "met"]
        flagged = {i for i, s in got.items() if s != "met"}
        row = {"policy": name, "obligations": len(expected), "real_gaps": len(real_gaps),
               "found": sum(i in flagged for i in real_gaps), "false_gaps": sum(i in flagged for i in compliant),
               "exact": sum(got.get(i) == s for i, s in expected.items()),
               "needs_review": sum(s == "needs_review" for s in got.values()), **summary(saved["findings"]),
               "errors": [{"id": i, "expected": expected[i], "got": got.get(i)} for i in expected
                          if got.get(i) != expected[i]]}
        rows.append(row)
        print(f"{name}: {row['found']}/{row['real_gaps']} gaps found, {row['false_gaps']} false gaps, "
              f"{row['exact']}/{row['obligations']} exact, {row['needs_review']} needs review", flush=True)

    total_gaps = sum(r["real_gaps"] for r in rows)
    total_ok = sum(r["obligations"] - r["real_gaps"] for r in rows)
    md = ["# Gap-analysis evaluation", "",
          f"Circular 2022-08 (complaint handling), {len(obligations)} reviewed obligations · 4 fictional bank policies "
          f"with known gaps · model `{llm.model}` · {time.strftime('%Y-%m-%d')}", "",
          f"**Gaps found: {sum(r['found'] for r in rows)} of {total_gaps}** · "
          f"**false gaps: {sum(r['false_gaps'] for r in rows)} of {total_ok} compliant obligations** · "
          f"exact status: {sum(r['exact'] for r in rows)} of {sum(r['obligations'] for r in rows)}", "",
          "| Policy | Real gaps | Found | False gaps | Exact status | Needs review |", "|---|---|---|---|---|---|"]
    md += [f"| {r['policy']} | {r['real_gaps']} | {r['found']} | {r['false_gaps']} | {r['exact']}/{r['obligations']} | "
           f"{r['needs_review']} |" for r in rows]
    md += ["", "## Every disagreement with the answer key", "", "| Policy | Obligation | Expected | Got |", "|---|---|---|---|"]
    md += [f"| {r['policy']} | {e['id']} | {e['expected']} | {e['got']} |" for r in rows for e in r["errors"]]
    (ROOT / "eval" / "gaps.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
