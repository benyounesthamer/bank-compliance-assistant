"""HTTP API and a one-page demo.

  uvicorn bankrag.api:app --port 8000      then open http://127.0.0.1:8000
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .answer import answer
from .llm import from_env
from .retrieve import MODES, load_retriever

ROOT = Path.cwd()
app = FastAPI(title="Bank regulation RAG", description="Cited answers from Tunisian central-bank circulars.")


@lru_cache
def retriever():
    return load_retriever(ROOT / "index")


@lru_cache
def llm():
    load_dotenv(ROOT / ".env")
    return from_env()


class Gaps(BaseModel):
    policy: str = Field(min_length=50, max_length=30000)
    circular: str = "2022-08"


@app.post("/gaps")
def gaps(body: Gaps) -> dict:
    """Check an internal policy against a circular's reviewed obligations."""
    from .gaps import check_policy, summary
    from .obligations import load_obligations
    path = ROOT / "data" / "obligations" / f"{body.circular}.json"
    if not path.exists():
        raise HTTPException(404, f"no reviewed obligations for circular {body.circular}")
    findings = check_policy(body.policy, load_obligations(path), llm())
    return {"circular": body.circular, "summary": summary(findings), "findings": findings}


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.post("/ask")
def ask(body: Ask) -> dict:
    out = answer(body.question, retriever(), llm())
    out.pop("retrieved")  # keep the response small; /search shows raw retrieval
    return out


@app.get("/search")
def search(q: str, mode: str = "hybrid_rerank", k: int = 5) -> list[dict]:
    if mode not in MODES:
        raise HTTPException(400, f"mode must be one of {MODES}")
    return retriever().search(q, mode, k=min(k, 20))


@app.get("/health")
def health() -> dict:
    return {"ok": True, "chunks": len(retriever().chunks)}


@app.get("/examples")
def examples() -> list[dict]:
    """The fictional test policies, so the demo can be tried without writing a policy."""
    folder = ROOT / "eval" / "policies"
    return [{"name": p.stem.replace("_", " ").title(), "text": p.read_text(encoding="utf-8")}
            for p in sorted(folder.glob("*.md"))]


@app.get("/", response_class=HTMLResponse)
def page() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
