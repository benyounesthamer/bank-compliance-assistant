"""Compliance gap analysis: check a bank's internal policy against a circular's obligations.

For each obligation the model gives a status and quotes the policy text it relied on. The code
then verifies every quote against the policy: a status that claims evidence the policy does not
contain is downgraded to "needs_review", so the report never cites words the bank did not write.
"""
from __future__ import annotations

import json
import re

from .obligations import ask_json_list, grounded
from .text import detect_language

STATUSES = ("met", "partial", "missing", "contradicts")
NEED_EVIDENCE = {"met", "partial", "contradicts"}
BATCH = 6  # obligations checked per model call

CHECK = """You are a banking compliance auditor. You check a bank's internal policy against obligations from a
Tunisian central-bank circular. For each obligation decide:
- "met": the policy clearly commits to it, with the same or a stricter figure/deadline/frequency
- "partial": the policy addresses it but leaves out part of it (e.g. only some of the required channels)
- "contradicts": the policy states something incompatible (e.g. a longer deadline, a rarer audit)
- "missing": the policy does not address it at all
Judge only from the policy text. A stricter commitment than required (e.g. 10 days instead of 15) is "met".
For met, partial and contradicts, "evidence" must be words copied character for character from the policy.
For missing, "evidence" is "".
Reply with a JSON array only, one item per obligation, in the order given:
{"id": "...", "status": "met | partial | contradicts | missing", "evidence": "...", "section": "policy section number or title",
 "explanation": "one sentence in {language}"}"""


def split_policy(text: str) -> list[dict]:
    """Sections by Markdown heading or numbered paragraph, so evidence can point to a place."""
    sections, title, buf = [], "Introduction", []
    for line in text.splitlines():
        if re.match(r"^\s*(#{1,4}\s+|\d+(\.\d+)*[.)]?\s+[A-ZÉÈÀ])", line):
            if "".join(buf).strip():
                sections.append({"title": title, "text": " ".join(" ".join(buf).split())})
            title, buf = line.strip("# ").strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append({"title": title, "text": " ".join(" ".join(buf).split())})
    return sections


def check_policy(policy: str, obligations: list[dict], llm) -> list[dict]:
    lang = {"fr": "French", "en": "English", "ar": "Arabic"}[detect_language(policy)]
    sections = split_policy(policy)
    numbered = "\n\n".join(f"[{s['title']}]\n{s['text']}" for s in sections)
    findings = []
    for i in range(0, len(obligations), BATCH):
        batch = obligations[i:i + BATCH]
        listing = "\n".join(f"- {o['id']} ({o['article']}): {o['obligation']}" for o in batch)
        items = ask_json_list(llm, CHECK.replace("{language}", lang),
                              f"Obligations:\n{listing}\n\nBank policy:\n{numbered}") or []
        by_id = {str(it.get("id")): it for it in items if isinstance(it, dict)}
        for o in batch:
            findings.append(verify(o, by_id.get(o["id"]), policy))
    return findings


def verify(obligation: dict, item: dict | None, policy: str) -> dict:
    """Turn the model's verdict into a finding, checking it against the policy text."""
    base = {k: obligation[k] for k in ("id", "article", "page", "obligation", "quote", "kind")}
    if not item:
        return {**base, "status": "needs_review", "evidence": "", "section": "",
                "explanation": "The model gave no verdict for this obligation."}
    status = str(item.get("status", "")).lower().strip()
    evidence = str(item.get("evidence", "")).strip().strip('"«»')
    finding = {**base, "status": status if status in STATUSES else "needs_review", "evidence": evidence,
               "section": str(item.get("section", "")), "explanation": str(item.get("explanation", ""))}
    if finding["status"] in NEED_EVIDENCE and not evidence_found(evidence, policy):
        finding.update(status="needs_review", claimed_status=status,
                       explanation=f"The model said '{status}' but its quote was not found in the policy. "
                                   + finding["explanation"])
    return finding


def evidence_found(evidence: str, policy: str) -> bool:
    """Every part of the quote must be in the policy. Models often join two passages with '...',
    so each part is checked on its own; very short parts carry no evidence and are ignored."""
    parts = [p.strip(" .;,") for p in re.split(r"\.\.\.|…|\[\.\.\.\]", evidence)]
    parts = [p for p in parts if len(p) >= 12]
    return bool(parts) and all(grounded(p, policy, threshold=0.85) for p in parts)


def summary(findings: list[dict]) -> dict:
    counts = {s: sum(f["status"] == s for f in findings) for s in (*STATUSES, "needs_review")}
    counts["total"] = len(findings)
    return counts


def to_json(findings: list[dict]) -> str:
    return json.dumps(findings, ensure_ascii=False, indent=1)
