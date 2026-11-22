"""Write an answer from retrieved passages, with checked citations, or refuse.

The model only sees numbered passages. It must cite them as [1], [2]... and reply NOT_FOUND
when they do not contain the answer. Its citations are then checked in code: a number that
does not match a passage it was given is dropped, and an answer with no valid citation is
turned into a refusal. So every claim that reaches the user points to a real article.
"""
from __future__ import annotations

import re

from .text import detect_language

LANG_NAMES = {"fr": "French", "en": "English", "ar": "Arabic"}
REFUSAL = {
    "fr": "Je n'ai pas trouvé la réponse dans les circulaires indexées.",
    "en": "I could not find the answer in the indexed circulars.",
    "ar": "لم أجد الإجابة في المناشير المفهرسة.",
}

SYSTEM = """You answer questions about Tunisian banking regulation using ONLY the numbered passages given.
Rules:
- Every sentence that states a fact must end with the number of the passage it comes from, like [2].
- If the passages do not contain the answer, reply exactly: NOT_FOUND
- If two circulars disagree, give the rule from the most recent one and mention the older value.
- Quote figures, deadlines and percentages exactly as written in the passage.
- Answer in {language}, in at most four sentences. Do not mention the passages themselves."""

TRANSLATE = """Translate this question about Tunisian banking regulation into French, the language of most of
the regulation texts. Keep figures and acronyms. Reply with the translated question only."""


def format_passages(hits: list[dict]) -> str:
    out = []
    for i, h in enumerate(hits, start=1):
        where = f"Circular {h['circular']} ({h['date']}), {h['article'] or 'preamble'}"
        out.append(f"[{i}] {where} — {h['title']}\n{h['text']}")
    return "\n\n".join(out)


def check_citations(text: str, n_passages: int) -> tuple[str, list[int]]:
    """Remove citations that point to no passage; return the cleaned text and valid numbers."""
    valid: list[int] = []

    def keep(m: re.Match) -> str:
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        good = [x for x in nums if 1 <= x <= n_passages]
        valid.extend(x for x in good if x not in valid)
        return "[" + ", ".join(map(str, good)) + "]" if good else ""

    cleaned = re.sub(r"\[\d+(?:\s*,\s*\d+)*\]", keep, text)
    return cleaned.strip(), valid


def answer(question: str, retriever, llm, k: int = 5, mode: str = "hybrid_rerank", translate: bool = True) -> dict:
    lang = detect_language(question)
    query = question
    if translate and lang != "fr":
        # most circulars exist only in French: search with a French version of the question too
        query = llm.complete(TRANSLATE, question).strip()
    hits = retriever.search(query, mode, k=k)
    reply = llm.complete(SYSTEM.format(language=LANG_NAMES[lang]),
                         f"Question: {question}\n\nPassages:\n{format_passages(hits)}").strip()
    text, cited = check_citations(reply, len(hits))
    if "NOT_FOUND" in reply or not cited:
        return {"question": question, "lang": lang, "answer": REFUSAL[lang], "refused": True,
                "sources": [], "search_query": query, "retrieved": hits}
    sources = [{"n": i, **{k: hits[i - 1][k] for k in ("circular", "date", "article", "page", "doc", "title")}}
               for i in cited]
    return {"question": question, "lang": lang, "answer": text, "refused": False,
            "sources": sources, "search_query": query, "retrieved": hits}
