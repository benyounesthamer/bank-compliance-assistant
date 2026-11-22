"""Publish the static demo (site/index.html) to a free Hugging Face static Space.

Usage: python deploy/build_static.py && python deploy/push_static_space.py <hf-username>
"""
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
README = """---
title: Bank Compliance Assistant
emoji: 🏦
colorFrom: blue
colorTo: green
sdk: static
pinned: false
license: mit
short_description: Compliance gap analysis on Tunisian banking rules
---

Real outputs of the Bank Compliance Assistant, saved from its evaluation: gap reports for four fictional bank
policies and 48 cited answers in French, English and Arabic, each next to the expected answer.

Code, method and full results: https://github.com/benyounesthamer/bank-compliance-assistant
"""

if len(sys.argv) != 2:
    raise SystemExit(__doc__)
repo_id = f"{sys.argv[1]}/bank-compliance-assistant"
api = HfApi()
api.create_repo(repo_id, repo_type="space", space_sdk="static", exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    (Path(tmp) / "README.md").write_text(README, encoding="utf-8")
    (Path(tmp) / "index.html").write_bytes((ROOT / "site" / "index.html").read_bytes())
    api.upload_folder(folder_path=tmp, repo_id=repo_id, repo_type="space", commit_message="Publish static demo")
print(f"https://huggingface.co/spaces/{repo_id}")
