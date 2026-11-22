"""Command line.

  bankrag download                 fetch the circulars listed in data/sources.json
  bankrag index                    parse the PDFs, chunk them and build the search index
  bankrag ask "your question"      answer with citations
  bankrag search "query" --mode bm25
  bankrag gaps policy.md           check an internal policy against a circular's obligations
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path.cwd()
SOURCES, PDFS, INDEX = ROOT / "data" / "sources.json", ROOT / "data" / "pdfs", ROOT / "index"


def download() -> None:
    import httpx
    meta = json.loads(SOURCES.read_text(encoding="utf-8"))
    PDFS.mkdir(parents=True, exist_ok=True)
    for d in meta["documents"]:
        out = PDFS / d["file"]
        if out.exists():
            continue
        r = httpx.get(meta["base_url"] + d["file"], headers={"User-Agent": "Mozilla/5.0"}, timeout=60,
                      follow_redirects=True)
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            out.write_bytes(r.content)
            print("downloaded", d["file"])
        else:
            print("FAILED", d["file"], r.status_code, file=sys.stderr)


def index() -> None:
    from .ingest import ingest, save
    from .retrieve import build_index
    chunks = ingest(SOURCES, PDFS)
    save(chunks, INDEX / "chunks.jsonl")
    build_index(chunks, INDEX)
    print(f"Indexed {len(chunks)} chunks from {len({c.doc for c in chunks})} documents.")


def main() -> None:
    p = argparse.ArgumentParser(prog="bankrag", description="Cited answers from Tunisian banking circulars.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("download")
    sub.add_parser("index")
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--no-translate", action="store_true", help="search with the question as written")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--mode", default="hybrid_rerank", choices=["bm25", "dense", "hybrid", "hybrid_rerank"])
    s.add_argument("-k", type=int, default=5)
    g = sub.add_parser("gaps", help="compliance gap analysis of an internal policy")
    g.add_argument("policy", type=Path, help="policy as a Markdown or text file")
    g.add_argument("--circular", default="2022-08", help="circular whose reviewed obligations are used")
    g.add_argument("--out", type=Path, default=Path("gap_report.html"))
    args = p.parse_args()
    load_dotenv(ROOT / ".env")

    if args.cmd == "gaps":
        from .gap_report import render_html, render_markdown
        from .gaps import check_policy, summary
        from .llm import from_env
        from .obligations import load_obligations
        obligations_file = ROOT / "data" / "obligations" / f"{args.circular}.json"
        meta = json.loads(obligations_file.read_text(encoding="utf-8"))
        title = next((c.title for c in __import__("bankrag.ingest", fromlist=["load"]).load(INDEX / "chunks.jsonl")
                      if c.circular == args.circular), "") if (INDEX / "chunks.jsonl").exists() else ""
        findings = check_policy(args.policy.read_text(encoding="utf-8"), load_obligations(obligations_file), from_env())
        args.out.write_text(render_html(findings, args.policy.name, args.circular, title), encoding="utf-8")
        args.out.with_suffix(".md").write_text(render_markdown(findings, args.policy.name, args.circular), encoding="utf-8")
        s_ = summary(findings)
        print(f"{s_['met']} met, {s_['partial']} partial, {s_['missing']} missing, {s_['contradicts']} contradicts, "
              f"{s_['needs_review']} needs review (of {len(meta['obligations'])}). Report: {args.out}")
    elif args.cmd == "download":
        download()
    elif args.cmd == "index":
        index()
    else:
        from .retrieve import load_retriever
        retriever = load_retriever(INDEX)
        if args.cmd == "search":
            for h in retriever.search(args.query, args.mode, k=args.k):
                print(f"{h['rank']}. {h['circular']} {h['article'] or 'preamble'} (p.{h['page']}) {h['text'][:150]}")
        else:
            from .answer import answer
            from .llm import from_env
            out = answer(args.question, retriever, from_env(), translate=not args.no_translate)
            print(out["answer"])
            for s_ in out["sources"]:
                print(f"  [{s_['n']}] Circular {s_['circular']} ({s_['date']}), {s_['article'] or 'preamble'}, "
                      f"page {s_['page']} — {s_['doc']}")


if __name__ == "__main__":
    main()
