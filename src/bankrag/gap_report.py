"""Gap report: a self-contained HTML page and a Markdown version."""
from __future__ import annotations

from html import escape

from .gaps import summary

LABELS = {"met": ("Met", "ok"), "partial": ("Partial", "warn"), "contradicts": ("Contradicts", "bad"),
          "missing": ("Missing", "bad"), "needs_review": ("Needs review", "muted")}
ORDER = {"contradicts": 0, "missing": 1, "partial": 2, "needs_review": 3, "met": 4}

CSS = """
:root{--bg:#f6f6f3;--card:#fff;--text:#1d1d1b;--muted:#6b6b65;--line:#e2e2dc;--ok:#1d7a46;--warn:#9a6a00;--bad:#b3261e;
--okbg:#e8f5ee;--warnbg:#fff4d6;--badbg:#fdecea;--mutedbg:#eeeeea}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--card:#1f1f1d;--text:#ededE8;--muted:#9b9b94;--line:#34342f;
--ok:#5cc98a;--warn:#e6b84a;--bad:#ff8a7e;--okbg:#17301f;--warnbg:#33290f;--badbg:#3a1c1a;--mutedbg:#2a2a27}}
*{box-sizing:border-box}body{margin:0;padding:32px 16px;background:var(--bg);color:var(--text);
font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:1040px;margin:0 auto}
h1{font-size:25px;margin:0 0 4px}h2{font-size:18px;margin:32px 0 12px}.muted{color:var(--muted)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.tile b{display:block;font-size:28px;line-height:1.1}.tile.ok b{color:var(--ok)}.tile.warn b{color:var(--warn)}.tile.bad b{color:var(--bad)}
.bar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--line);margin:4px 0 8px}
.bar i{display:block;height:100%}.bar .ok{background:var(--ok)}.bar .warn{background:var(--warn)}.bar .bad{background:var(--bad)}.bar .muted{background:var(--muted)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.tag{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;white-space:nowrap}
.tag.ok{background:var(--okbg);color:var(--ok)}.tag.warn{background:var(--warnbg);color:var(--warn)}
.tag.bad{background:var(--badbg);color:var(--bad)}.tag.muted{background:var(--mutedbg);color:var(--muted)}
.src{font-size:13px;color:var(--muted);white-space:nowrap}.ev{font-style:italic}.why{color:var(--muted);font-size:14px;margin-top:4px}
td.ob{width:38%}td.ev-cell{width:40%}
@media (max-width:700px){td.ob,td.ev-cell{width:auto}.src{white-space:normal}}
"""


def render_html(findings: list[dict], policy_name: str, circular: str, title: str) -> str:
    s = summary(findings)
    e = escape
    total = max(s["total"], 1)
    gaps = s["missing"] + s["partial"] + s["contradicts"]
    h = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
         f"content='width=device-width, initial-scale=1'><title>Gap report</title><style>{CSS}</style></head><body><main>",
         f"<h1>Compliance gap report</h1><div class='muted'>{e(policy_name)} checked against circular "
         f"{e(circular)} — {e(title)} · {s['total']} obligations</div>",
         "<div class='tiles'>",
         f"<div class='tile ok'><b>{s['met']}</b>met</div>",
         f"<div class='tile warn'><b>{s['partial']}</b>partial</div>",
         f"<div class='tile bad'><b>{s['missing']}</b>missing</div>",
         f"<div class='tile bad'><b>{s['contradicts']}</b>contradicts</div>",
         f"<div class='tile'><b>{s['needs_review']}</b>needs review</div></div>",
         "<div class='bar'>" + "".join(
             f"<i class='{LABELS[k][1]}' style='width:{100 * s[k] / total}%'></i>"
             for k in ("met", "partial", "missing", "contradicts", "needs_review")) + "</div>",
         f"<p>{gaps} gap(s) to fix. Every quote below was checked against the policy text; "
         "a verdict whose quote could not be found is shown as <i>needs review</i>.</p>",
         "<h2>Findings</h2><table><tr><th>Status</th><th>Obligation</th><th>Evidence in the policy</th></tr>"]
    for f in sorted(findings, key=lambda f: (ORDER.get(f["status"], 9), f["id"])):
        label, cls = LABELS.get(f["status"], (f["status"], "muted"))
        evidence = f"<div class='ev'>“{e(f['evidence'])}”</div>" if f["evidence"] else "<div class='muted'>Not found in the policy</div>"
        where = f" <span class='src'>· {e(f['section'])}</span>" if f.get("section") and f["evidence"] else ""
        h.append(f"<tr><td><span class='tag {cls}'>{label}</span></td>"
                 f"<td class='ob'>{e(f['obligation'])}<div class='src'>{e(f['id'])} · {e(f['article'])}, page {f['page']}</div></td>"
                 f"<td class='ev-cell'>{evidence}{where}<div class='why'>{e(f['explanation'])}</div></td></tr>")
    h.append("</table><p class='muted'>Automated analysis to support a compliance review; not legal advice.</p>"
             "</main></body></html>")
    return "\n".join(h)


def render_markdown(findings: list[dict], policy_name: str, circular: str) -> str:
    s = summary(findings)
    out = [f"# Gap report: {policy_name} vs circular {circular}", "",
           f"{s['met']} met · {s['partial']} partial · {s['missing']} missing · {s['contradicts']} contradicts · "
           f"{s['needs_review']} needs review (of {s['total']})", "",
           "| Status | Obligation | Source | Evidence |", "|---|---|---|---|"]
    for f in sorted(findings, key=lambda f: (ORDER.get(f["status"], 9), f["id"])):
        out.append(f"| {LABELS.get(f['status'], (f['status'],))[0]} | {f['obligation']} | {f['article']} | "
                   f"{f['evidence'].replace('|', '/') or '—'} |")
    return "\n".join(out) + "\n"
