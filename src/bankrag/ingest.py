"""PDF circulars -> chunks with the metadata a citation needs (document, article, page)."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader

# "Article 3", "Article premier", "Art. 12", "ARTICLE 4 :" / Arabic "الفصل 3", "الفصل الأول"
ARTICLE = re.compile(
    r"(?m)^\s*(?:(?:article|art\.)\s*(?:\d+(?:\s*bis)?|premier|1er)\b"
    r"|الفصل\s*(?:\d+|ال[؀-ۿ]+))", re.IGNORECASE)
NUMBER_FILE = re.compile(r"(\d{4})\s*[-_]\s*(\d{2})")
NUMBER_FR = re.compile(r"n\s*°\s*(\d{4})\s*[-–]\s*(\d{1,3})", re.I)
NUMBER_AR = re.compile(r"عدد\s*(\d{1,3})\s*لسنة\s*(\d{4})")
SPACED = re.compile(r"\b(?:\w ){3,}\w\b")  # "T r a n s f e r t s" -> "Transferts"


@dataclass
class Chunk:
    id: str
    doc: str          # file name of the source PDF
    lang: str
    circular: str     # e.g. "2024-01"
    title: str        # the circular's subject ("Objet")
    article: str      # e.g. "Article 3", or "" for the preamble
    page: int         # 1-based page where the chunk starts
    date: str         # date of the circular as written in it
    text: str


def read_pages(path: Path) -> list[str]:
    return [p.extract_text() or "" for p in PdfReader(path).pages]


def find_title(text: str, lang: str) -> str:
    text = text[:2500]  # the subject is in the header; deeper matches are body text
    if lang == "ar":
        m = re.search(r"الموضوع\s*:?\s*(.{5,160}?)[\.\n]", text)
    else:
        m = (re.search(r"o\s*b\s*j\s*e\s*t\s*:?\s*(.{5,200}?)(?:\.\s|\n\s*\n|Le Gouverneur)", text, re.I | re.S)
             # some circulars have no "Objet": the title follows the number, up to "Le Gouverneur"
             or re.search(r"n\s*°\s*\d{4}\s*[-–]\s*\d{1,3}\s+(.{10,300}?)\s*Le Gouverneur", text, re.I | re.S))
    if not m:
        return ""
    raw = m.group(1)
    if SPACED.search(raw):  # "T r a n s f e r t s  a u": single spaces inside words, double between
        raw = re.sub(r"(?<=\b\w) (?=\w\b)", "", raw)
    return " ".join(raw.split())


def find_number(name: str, text: str) -> str:
    """The circular's own number, read from its header; the file name is only a fallback."""
    head = text[:900]
    if m := NUMBER_FR.search(head):
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    if m := NUMBER_AR.search(head):
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    m = NUMBER_FILE.search(name)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def find_date(text: str) -> str:
    m = (re.search(r"Tunis\s*,?\s*le\s*([^\n]{6,30})", text, re.I)
         or re.search(r"تونس،?\s*في\s*([^\n]{4,30})", text))
    return " ".join(m.group(1).split()) if m else ""


def clean_label(label: str) -> str:
    """'Article7' -> 'Article 7', 'ARTICLE PREMIER' -> 'Article premier', 'الفصل36' -> 'الفصل 36'."""
    label = re.sub(r"(?<=[^\W\d_])(?=\d)", " ", " ".join(label.split()))
    return label[:1].upper() + label[1:].lower() if label.isascii() else label


def split_articles(pages: list[str]) -> list[tuple[str, int, str]]:
    """Return (article label, start page, text) for the preamble and each article."""
    parts, label, page, buf = [], "", 1, []
    for pno, page_text in enumerate(pages, start=1):
        pos = 0
        for m in ARTICLE.finditer(page_text):
            buf.append(page_text[pos:m.start()])
            if "".join(buf).strip():
                parts.append((label, page, "".join(buf)))
            label, page, buf, pos = clean_label(m.group(0)), pno, [], m.start()
        buf.append(page_text[pos:] + "\n")
    if "".join(buf).strip():
        parts.append((label, page, "".join(buf)))
    return parts


def window(text: str, size: int = 700, overlap: int = 150) -> list[str]:
    """Cut long text into overlapping pieces, preferring to cut at a sentence end.

    700 characters is about 150-200 tokens: the multilingual embedding model reads only
    the first 128 tokens, so longer pieces would be partly invisible to vector search.
    """
    text = " ".join(text.split())
    if len(text) <= size:
        return [text]
    pieces, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(text.rfind(". ", start + size // 2, end), text.rfind("; ", start + size // 2, end))
            end = cut + 1 if cut > 0 else end
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return pieces


def chunk_document(path: Path, lang: str, overrides: dict | None = None) -> list[Chunk]:
    """`overrides` (from sources.json) fixes metadata a PDF gets wrong, e.g. a broken font."""
    pages = read_pages(path)
    full = "\n".join(pages)
    o = overrides or {}
    title = o.get("title") or find_title(full, lang)
    number = o.get("circular") or find_number(path.name, full)
    date = o.get("date") or find_date(full)
    chunks = []
    for label, page, text in split_articles(pages):
        for piece in window(text):
            if len(piece) < 40:  # page numbers, stray headers
                continue
            chunks.append(Chunk(f"{path.stem}#{len(chunks)}", path.name, lang, number, title, label, page, date, piece))
    return chunks


def ingest(sources: Path, pdf_dir: Path) -> list[Chunk]:
    meta = json.loads(sources.read_text(encoding="utf-8"))
    chunks = []
    for d in meta["documents"]:
        path = pdf_dir / d["file"]
        if path.exists():
            chunks.extend(chunk_document(path, d["lang"], d.get("override")))
    return chunks


def save(chunks: list[Chunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


def load(path: Path) -> list[Chunk]:
    return [Chunk(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
