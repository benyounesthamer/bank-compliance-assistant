"""Build a static, self-contained demo page from the saved evaluation results.

Free static hosting cannot run the models, so this page shows real outputs instead: the full gap
report for each example policy, and every evaluated question with its answer, sources and verdict.
Nothing runs live, so it costs no API quota.

Usage: python deploy/build_static.py      -> site/index.html
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/benyounesthamer/bank-compliance-assistant"


def main() -> None:
    labels = json.loads((ROOT / "eval/policies/labels.json").read_text(encoding="utf-8"))
    policies = []
    for path in sorted((ROOT / "eval/policies").glob("*.md")):
        saved = json.loads((ROOT / "eval/gaps" / f"{path.stem}.json").read_text(encoding="utf-8"))
        expected = labels.get(path.name, {})
        for f in saved["findings"]:
            f["expected"] = expected.get(f["id"], "met")
        policies.append({"name": path.stem.replace("_", " ").title(), "text": path.read_text(encoding="utf-8"),
                         "findings": saved["findings"], "model": saved["model"]})
    questions = {json.loads(l)["id"]: json.loads(l)
                 for l in (ROOT / "eval/questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    answers = []
    for line in (ROOT / "eval/answers.jsonl").read_text(encoding="utf-8").splitlines():
        a = json.loads(line)
        q = questions[a["id"]]
        answers.append({"id": a["id"], "lang": a["lang"], "question": q["question"], "reference": q["answer"],
                        "answer": a["answer"], "cited": a["cited"], "correct": a["correct"],
                        "answerable": a["answerable"], "refused": a["refused"], "judge": a.get("judge_reason", "")})
    data = json.dumps({"policies": policies, "answers": answers}, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.replace("__DATA__", data).replace("__REPO__", REPO)
    out = ROOT / "site"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    print(f"site/index.html: {len(policies)} policies, {len(answers)} answers, {len(page) // 1024} KB")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bank Compliance Assistant</title>
<style>
:root{--bg:#f6f6f3;--card:#fff;--text:#1d1d1b;--muted:#6b6b65;--line:#e2e2dc;--accent:#1f5f8b;
--ok:#1d7a46;--warn:#9a6a00;--bad:#b3261e;--okbg:#e8f5ee;--warnbg:#fff4d6;--badbg:#fdecea;--mutedbg:#eeeeea}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--card:#1f1f1d;--text:#ededE8;--muted:#9b9b94;--line:#34342f;--accent:#7cb7e0;
--ok:#5cc98a;--warn:#e6b84a;--bad:#ff8a7e;--okbg:#17301f;--warnbg:#33290f;--badbg:#3a1c1a;--mutedbg:#2a2a27}}
*{box-sizing:border-box}body{margin:0;padding:32px 16px;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:920px;margin:0 auto}h1{font-size:26px;margin:0 0 4px}p.sub{color:var(--muted);margin:0 0 10px}
.note{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font-size:14px;color:var(--muted);margin:14px 0 20px}
a{color:var(--accent)}
.tabs{display:flex;gap:6px;margin-bottom:18px;border-bottom:1px solid var(--line)}
.tabs button{background:none;border:0;border-bottom:2px solid transparent;padding:8px 14px;font:inherit;color:var(--muted);cursor:pointer}
.tabs button.on{color:var(--text);border-color:var(--accent);font-weight:600}
select,input{padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--text);font:inherit}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
details{margin:6px 0 14px}summary{cursor:pointer;color:var(--accent);font-size:14px}
pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;font-size:13px;max-height:340px;overflow:auto}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin:8px 0 16px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font-size:14px}
.tile b{display:block;font-size:24px}.tile.ok b{color:var(--ok)}.tile.warn b{color:var(--warn)}.tile.bad b{color:var(--bad)}
.item{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:8px 0}
.tag{display:inline-block;padding:1px 9px;border-radius:99px;font-size:12px;font-weight:600;margin-right:6px}
.tag.ok{background:var(--okbg);color:var(--ok)}.tag.warn{background:var(--warnbg);color:var(--warn)}
.tag.bad{background:var(--badbg);color:var(--bad)}.tag.muted{background:var(--mutedbg);color:var(--muted)}
.ev{font-style:italic;margin-top:6px}.why,.meta{color:var(--muted);font-size:14px}.q{font-weight:600}
[dir=rtl]{text-align:right}[hidden]{display:none!important}
</style></head><body><main>
<h1>Bank Compliance Assistant</h1>
<p class="sub">Compliance gap analysis and cited answers on Tunisian central-bank circulars.</p>
<div class="note">These are <b>real, unedited outputs</b> saved from the project's evaluation (model <code>gpt-oss-20b</code>), shown
next to the expected answers so you can judge them, mistakes included. Nothing runs live on this page.
Code, method and full results: <a href="__REPO__">GitHub</a>.</div>
<div class="tabs"><button class="on" data-tab="gaps">Gap analysis</button><button data-tab="qa">Questions &amp; answers</button></div>

<section id="gaps">
  <div class="row"><select id="pol"></select></div>
  <details><summary>Show the policy text</summary><pre id="ptext"></pre></details>
  <div id="gout"></div>
</section>

<section id="qa" hidden>
  <div class="row"><select id="lang"><option value="">All languages</option><option value="fr">French</option>
  <option value="en">English</option><option value="ar">Arabic</option></select>
  <select id="res"><option value="">All results</option><option value="ok">Correct</option><option value="bad">Wrong or refused</option></select>
  <input id="find" placeholder="Search questions"></div>
  <div id="qout"></div>
</section>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => {
  document.querySelectorAll('.tabs button').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('main > section').forEach(s => s.hidden = s.id !== b.dataset.tab);
});
const LABEL = {met:['Met','ok'], partial:['Partial','warn'], missing:['Missing','bad'], contradicts:['Contradicts','bad'], needs_review:['Needs review','muted']};
const ORDER = {contradicts:0, missing:1, partial:2, needs_review:3, met:4};
D.policies.forEach((p, i) => { const o = document.createElement('option'); o.value = i; o.textContent = p.name; $('pol').append(o); });
$('pol').value = String(D.policies.findIndex(p => /gamma/i.test(p.name)));
function showPolicy() {
  const p = D.policies[$('pol').value];
  $('ptext').textContent = p.text;
  const n = k => p.findings.filter(f => f.status === k).length;
  const agree = p.findings.filter(f => f.status === f.expected).length;
  const tiles = [['met','ok'],['partial','warn'],['missing','bad'],['contradicts','bad'],['needs_review','']]
    .map(([k, c]) => `<div class="tile ${c}"><b>${n(k)}</b>${k.replace('_', ' ')}</div>`).join('');
  const items = [...p.findings].sort((a, b) => ORDER[a.status] - ORDER[b.status]).map(f => {
    const [label, cls] = LABEL[f.status] || [f.status, 'muted'];
    const ev = f.evidence ? `<div class="ev">“${esc(f.evidence)}”</div>` : '<div class="meta">Not found in the policy</div>';
    const key = f.status === f.expected ? '' : ` · <b style="color:var(--bad)">answer key says: ${esc(f.expected)}</b>`;
    return `<div class="item"><span class="tag ${cls}">${label}</span>${esc(f.obligation)}
      <div class="meta">${esc(f.id)} · ${esc(f.article)}, page ${f.page}${key}</div>${ev}<div class="why">${esc(f.explanation)}</div></div>`;
  }).join('');
  $('gout').innerHTML = `<div class="tiles">${tiles}</div><p class="meta">${agree} of ${p.findings.length} verdicts match the answer key.</p>${items}`;
}
$('pol').onchange = showPolicy; showPolicy();
function showQA() {
  const lang = $('lang').value, res = $('res').value, term = $('find').value.toLowerCase();
  const rows = D.answers.filter(a => (!lang || a.lang === lang) && (!res || (res === 'ok') === a.correct)
    && (!term || a.question.toLowerCase().includes(term)));
  $('qout').innerHTML = `<p class="meta">${rows.filter(a => a.correct).length} of ${rows.length} judged correct.</p>` + rows.map(a => {
    const dir = a.lang === 'ar' ? 'rtl' : 'ltr';
    const tag = a.correct ? '<span class="tag ok">Correct</span>' : (a.refused && a.answerable ? '<span class="tag warn">Refused</span>' : '<span class="tag bad">Wrong</span>');
    const kind = a.answerable ? '' : '<span class="tag muted">not answerable from the circulars</span>';
    const src = a.cited.length ? `<div class="meta">Cited: ${a.cited.map(esc).join(' · ')}</div>` : '';
    const judge = !a.correct && a.judge ? `<div class="why">Judge: ${esc(a.judge)}</div>` : '';
    return `<div class="item">${tag}${kind}<div class="q" dir="${dir}">${esc(a.question)}</div>
      <div dir="${dir}">${esc(a.answer)}</div>${src}<div class="meta" dir="${dir}">Expected: ${esc(a.reference)}</div>${judge}</div>`;
  }).join('');
}
['lang', 'res'].forEach(id => $(id).onchange = showQA); $('find').oninput = showQA; showQA();
</script></main></body></html>"""

if __name__ == "__main__":
    main()
