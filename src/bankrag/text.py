"""Text normalisation shared by indexing and search, for French, Arabic and English."""
from __future__ import annotations

import re
import unicodedata

ARABIC_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # harakat + tatweel
WORD = re.compile(r"\w+", re.UNICODE)

STOPWORDS = set("""
le la les un une des du de d l à au aux et ou en dans par pour sur avec sans ce cette ces qui que quoi dont
est sont été être a ont il elle ils elles se sa son ses leur leurs nous vous ne pas plus y lui même
the a an of to in on for and or is are be by with as at from that this which what how does do can
في من على إلى الى عن مع أن ان هذا هذه التي الذي ما هل كيف او أو و ب ل ك
""".split())


def normalize_arabic(text: str) -> str:
    text = ARABIC_DIACRITICS.sub("", text)
    text = re.sub("[إأآٱ]", "ا", text)
    return text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")


def fold(text: str) -> str:
    """Lowercase, strip Latin accents, normalise Arabic letter variants."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c) or "؀" <= c <= "ۿ")
    return normalize_arabic(unicodedata.normalize("NFC", text))


def tokenize(text: str) -> list[str]:
    """Tokens for keyword search. Arabic 'al-' is split off so 'البنك' matches 'بنك'."""
    tokens = []
    for t in WORD.findall(fold(text)):
        if len(t) > 3 and t.startswith("ال"):
            t = t[2:]
        if t not in STOPWORDS and (len(t) > 1 or t.isdigit()):
            tokens.append(t)
    return tokens


def detect_language(text: str) -> str:
    """Rough language guess, good enough to answer in the user's language."""
    arabic = sum("؀" <= c <= "ۿ" for c in text)
    if arabic > len(text) * 0.2:
        return "ar"
    words = set(WORD.findall(text.lower()))
    french = len(words & {"le", "la", "les", "des", "du", "est", "quel", "quelle", "quels", "quelles", "pour",
                          "une", "dans", "banque", "banques", "délai", "doit", "doivent", "comment"})
    english = len(words & {"the", "what", "which", "is", "are", "how", "must", "bank", "banks", "within",
                           "does", "should", "deadline"})
    return "fr" if french >= english else "en"
