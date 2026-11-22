"""Publish the demo to a Hugging Face Space (Docker).

Prerequisites: a Hugging Face account, `pip install huggingface_hub`, and `hf auth login`
(the token never goes in this repository). The API key for the model is set as a Space secret
named GROQ_API_KEY in the Space settings, not here.

Usage: python deploy/push_space.py <hf-username>
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["Dockerfile", ".dockerignore", "pyproject.toml", "LICENSE", "src", "data/sources.json",
           "data/obligations", "eval/policies", "eval/gaps", "eval/questions.jsonl"]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    repo_id = f"{sys.argv[1]}/bank-compliance-assistant"
    api = HfApi()
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for item in INCLUDE:
            src = ROOT / item
            dst = out / item
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.html"))
            else:
                shutil.copy2(src, dst)
        shutil.copy2(ROOT / "deploy" / "space_README.md", out / "README.md")
        api.upload_folder(folder_path=str(out), repo_id=repo_id, repo_type="space",
                          commit_message="Deploy Bank Compliance Assistant")
    print(f"Pushed. Add the GROQ_API_KEY secret at https://huggingface.co/spaces/{repo_id}/settings")
    print(f"Demo: https://huggingface.co/spaces/{repo_id}")


if __name__ == "__main__":
    main()
