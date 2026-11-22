"""Turn a circular into a list of atomic, checkable obligations, each grounded in a verbatim quote.

The model proposes obligations article by article; the code keeps only those whose quote really
appears in the article. The result is saved and reviewed once, so every gap analysis checks
policies against the same list.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from .ingest import read_pages, split_articles

EXTRACT = """You turn one article of a Tunisian banking circular into atomic obligations that a bank's
internal policy must address. An obligation is one thing the bank must do, have, or not exceed.
Split lists: "channels: e-mail, online form, branch" gives one obligation per channel.
Keep exact figures, deadlines and frequencies. Ignore definitions, scope statements, entry-into-force
dates, reporting templates sent to the central bank, and references to other texts.
Reply with a JSON array only (it may be empty). Each item:
{"obligation": "one sentence in French, starting with 'L'établissement doit'",
 "quote": "the exact words of the article that impose it, copied character for character",
 "kind": "deadline | frequency | channel | content | organisation | reporting | other"}"""


def normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("«", '"').replace("»", '"').replace("−", "-")
    return " ".join(text.split()).lower()


def grounded(quote: str, article: str, threshold: float = 0.9) -> bool:
    """True if the quote appears in the article, allowing tiny differences from PDF extraction."""
    q, a = normalize(quote), normalize(article)
    if len(q) < 12:
        return False
    if q in a:
        return True
    matcher = difflib.SequenceMatcher(None, a, q, autojunk=False)
    block = matcher.find_longest_match(0, len(a), 0, len(q))
    start = max(0, block.a - block.b)
    window = a[start:start + len(q) + 10]
    return difflib.SequenceMatcher(None, window, q).ratio() >= threshold


def article_texts(pdf: Path) -> list[tuple[str, int, str]]:
    return [(label, page, " ".join(text.split())) for label, page, text in split_articles(read_pages(pdf))
            if label]


def ask_json_list(llm, system: str, user: str, attempts: int = 3) -> list | None:
    """Ask for a JSON array; retry on an empty or unparsable reply. None means every attempt failed,
    which is different from an empty list (the model found nothing)."""
    for _ in range(attempts):
        reply = llm.complete(system, user)
        start, end = reply.find("["), reply.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(reply[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def extract(pdf: Path, circular: str, llm) -> dict:
    obligations, rejected, failed = [], [], []
    for label, page, text in article_texts(pdf):
        items = ask_json_list(llm, EXTRACT, f"Circular {circular}, {label}:\n{text[:3500]}")
        if items is None:  # never silently skip an article: report it so it can be redone or done by hand
            failed.append(label)
            continue
        for item in items:
            if not isinstance(item, dict) or not item.get("obligation"):
                continue
            entry = {"article": label, "page": page, "obligation": item["obligation"].strip(),
                     "quote": str(item.get("quote", "")).strip(), "kind": item.get("kind", "other")}
            (obligations if grounded(entry["quote"], text) else rejected).append(entry)
    for i, o in enumerate(obligations, start=1):
        o["id"] = f"{circular}-O{i:02d}"
    return {"circular": circular, "source": pdf.name, "obligations": obligations, "rejected": rejected,
            "failed_articles": failed}


def load_obligations(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["obligations"]


def save(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


