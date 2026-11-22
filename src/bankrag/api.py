"""HTTP API and a one-page demo.

  uvicorn bankrag.api:app --port 8000      then open http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .answer import answer
from .llm import from_env
from .retrieve import MODES, load_retriever

ROOT = Path.cwd()
app = FastAPI(title="Bank Compliance Assistant",
              description="Gap analysis and cited answers over Tunisian central-bank circulars.")

# A public demo runs on the owner's API quota, so live model calls are limited per visitor.
# 0 means no limit (local use). The example policies are served from saved results and are never limited.
LIVE_PER_HOUR = int(os.getenv("DEMO_LIVE_REQUESTS_PER_HOUR", "0"))
_recent: dict[str, deque] = defaultdict(deque)


def check_rate(request: Request) -> None:
    if LIVE_PER_HOUR <= 0:
        return
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    now, q = time.time(), _recent[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= LIVE_PER_HOUR:
        raise HTTPException(429, f"This public demo allows {LIVE_PER_HOUR} live requests per hour. "
                                 "The example policies always work, or run the project locally.")
    q.append(now)


@lru_cache
def cached_examples() -> dict[str, dict]:
    """Saved evaluation results for the example policies, keyed by their exact text."""
    out = {}
    for path in (ROOT / "eval" / "policies").glob("*.md"):
        saved = ROOT / "eval" / "gaps" / f"{path.stem}.json"
        if saved.exists():
            out[path.read_text(encoding="utf-8").strip()] = json.loads(saved.read_text(encoding="utf-8"))
    return out


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
def gaps(body: Gaps, request: Request) -> dict:
    """Check an internal policy against a circular's reviewed obligations."""
    from .gaps import check_policy, summary
    from .obligations import load_obligations
    path = ROOT / "data" / "obligations" / f"{body.circular}.json"
    if not path.exists():
        raise HTTPException(404, f"no reviewed obligations for circular {body.circular}")
    saved = cached_examples().get(body.policy.strip())
    if saved and body.circular == "2022-08":
        return {"circular": body.circular, "summary": summary(saved["findings"]), "findings": saved["findings"],
                "cached": True, "model": saved.get("model")}
    check_rate(request)
    findings = check_policy(body.policy, load_obligations(path), llm())
    return {"circular": body.circular, "summary": summary(findings), "findings": findings, "cached": False}


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.post("/ask")
def ask(body: Ask, request: Request) -> dict:
    check_rate(request)
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
