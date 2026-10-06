"""Self-contained HTML. Escape all experimental content; no external requests."""

import difflib
import html
import json
import re
import statistics
from collections import Counter
from pathlib import Path

STATUSES = {"passed", "failed", "error", "timeout"}


def summarize(manifest, rows):
    baseline = {(r["task"], r["repeat"]): r for r in rows if r["variant"] == "v0"}
    result = []
    for variant in manifest["variants"]:
        selected = [r for r in rows if r["variant"] == variant["id"]]
        counts = Counter(r["status"] for r in selected)
        pairs = [
            (r, baseline[(r["task"], r["repeat"])])
            for r in selected
            if (r["task"], r["repeat"]) in baseline
            and r["status"] in {"passed", "failed"}
            and baseline[(r["task"], r["repeat"])]["status"] in {"passed", "failed"}
        ]
        times = [r["runner_seconds"] for r in selected if r["runner_seconds"] is not None]
        usage = [r["usage"] for r in selected if r["usage"] is not None]
        result.append(
            {
                **variant,
                "attempted": len(selected),
                "passed": counts["passed"],
                "failed": counts["failed"],
                "errors": counts["error"],
                "timeouts": counts["timeout"],
                "median_seconds": statistics.median(times) if times else None,
                "usage_coverage": len(usage),
                "tokens": sum(u["input_tokens"] + u["output_tokens"] for u in usage)
                if usage
                else None,
                "cached": sum(u["cached_input_tokens"] for u in usage) if usage else None,
                "paired": len(pairs),
                "wins": sum(a["status"] == "passed" and b["status"] == "failed" for a, b in pairs),
                "losses": sum(
                    a["status"] == "failed" and b["status"] == "passed" for a, b in pairs
                ),
                "ties": sum(a["status"] == b["status"] for a, b in pairs),
            }
        )
    return result


def write_report(directory: Path):
    directory = directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((directory / "results.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported result schema.")
    for row in rows:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*-v[0-9]+-r[0-9]+", row["id"]):
            raise ValueError("Invalid trial ID in results.")
        if row["status"] not in STATUSES:
            raise ValueError("Invalid trial status in results.")

    def esc(value):
        return html.escape(str(value), quote=True)

    demo = manifest["mode"] == "demo"
    summaries = summarize(manifest, rows)
    labels = {v["id"]: v["label"] for v in manifest["variants"]}
    per_variant = len(manifest["tasks"]) * manifest["repeats"]
    summary_rows = []
    for item in summaries:
        percent = 100 * item["passed"] / item["attempted"] if item["attempted"] else 0
        time = "—" if demo or item["median_seconds"] is None else f"{item['median_seconds']:.1f}s"
        tokens = "—" if item["tokens"] is None else f"{item['tokens']:,}"
        cached = "—" if item["cached"] is None else f"{item['cached']:,}"
        coverage = f"{item['usage_coverage']}/{item['attempted']} reported"
        pairs = (
            "Baseline"
            if item["id"] == "v0"
            else f"{item['wins']} wins / {item['losses']} losses / {item['ties']} ties"
            f"<small>{item['paired']} valid pairs</small>"
        )
        summary_rows.append(
            f'<tr><th scope="row">{esc(item["label"])}</th>'
            f"<td><strong>{item['passed']} / {item['attempted']}</strong>"
            '<div class="track" aria-hidden="true">'
            f'<span style="width:{percent:.2f}%"></span></div>'
            f"<small>{item['attempted']}/{per_variant} scheduled attempts</small></td>"
            f"<td>{item['failed']} failed<small>{item['errors']} errors, "
            f"{item['timeouts']} timeouts</small></td>"
            f"<td>{time}</td><td>{tokens}<small>{coverage}; {cached} cached</small></td>"
            f"<td>{pairs}</td></tr>"
        )
    matrix = []
    lookup = {(r["task"], r["variant"], r["repeat"]): r for r in rows}
    for task in manifest["tasks"]:
        cells = []
        for variant in manifest["variants"]:
            dots = []
            for repeat in range(1, manifest["repeats"] + 1):
                trial = lookup.get((task["id"], variant["id"], repeat))
                if trial:
                    status = trial["status"]
                    dots.append(
                        f'<a class="trial {status}" href="#{esc(trial["id"])}" '
                        f'aria-label="{esc(task["title"])}; {esc(variant["label"])}; '
                        f'repeat {repeat}: {status}">{repeat} {status}</a>'
                    )
                else:
                    dots.append(f'<span class="trial pending">{repeat} not run</span>')
            cells.append("<td>" + "".join(dots) + "</td>")
        matrix.append(f'<tr><th scope="row">{esc(task["title"])}</th>{"".join(cells)}</tr>')

    def read_artifact(path):
        resolved = path.resolve()
        if not resolved.is_relative_to(directory):
            raise ValueError("Artifact points outside the experiment directory.")
        if not path.exists():
            return "(not available)"
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:40_000] + (
            "\n[Report display truncated; full text is in the run folder.]"
            if len(text) > 40_000
            else ""
        )

    details = []
    for row in rows:
        folder = directory / row["id"]
        source = read_artifact(folder / "solution.py")
        before = read_artifact(folder / "starter.py")
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                source.splitlines(keepends=True),
                fromfile="initial.py",
                tofile="solution.py",
            )
        )
        if not diff:
            diff = "(No code changes.)\n"
        tests = read_artifact(folder / "grading" / "stderr.txt")
        error = f'<p class="error-text">{esc(row["error"])}</p>' if row["error"] else ""
        details.append(
            f'<details class="evidence" id="{esc(row["id"])}" data-status="{row["status"]}">'
            f'<summary><span class="status {row["status"]}">{row["status"]}</span> '
            f"{esc(row['task'])} / {esc(labels[row['variant']])} / repeat {row['repeat']}"
            "</summary>"
            + error
            + f'<div class="evidence-body"><h3>Code change</h3><pre>{esc(diff)}</pre>'
            f"<h3>Test output</h3><pre>{esc(tests)}</pre>"
            f"<h3>Task prompt</h3><pre>{esc(read_artifact(folder / 'prompt.txt'))}</pre>"
            f"<p>Full evidence folder: <code>{esc(row['id'])}</code></p></div></details>"
        )
    css = Path(__file__).with_name("report.css").read_text(encoding="utf-8")
    warning = (
        "Scripted demo · No model was called. Outcomes come from chosen code fixtures, "
        "not measured skill performance."
        if demo
        else "Exploratory live run · Results apply to these tasks and this setup. "
        "Small samples do not establish a universally better skill."
    )
    state = manifest["status"]
    pack_name = manifest.get("task_pack", {}).get("name", "Bundled Python repairs")
    completeness = (
        "All scheduled trials finished."
        if state == "complete"
        else "Incomplete experiment. Remaining trials were not run; do not rank these conditions."
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Skill Compare Lab — comparison report</title>
<style>{css}</style>
</head>
<body>
<header><a class="brand" href="#top">
<span class="mark" aria-hidden="true">≋</span> Skill Compare Lab</a>
<span class="run-mode">{"Scripted demo" if demo else "Live experiment"}</span></header>
<main id="top">
<section class="intro">
<h1>What changed<br>with the skill?</h1>
<div><p class="lead">One task pack. A shared baseline.<br>Every attempt kept for inspection.</p>
<p>{len(manifest["tasks"])} tasks × {len(manifest["variants"])} conditions ×
{manifest["repeats"]} repeats</p></div>
</section>
<p class="notice">{warning}</p>
<div class="protocol"><span><b>Model</b> {esc(manifest["model"])}</span>
<span><b>Grader</b> {esc(manifest["executor"])}</span>
<span><b>Task pack</b> {esc(pack_name)}</span>
<span><b>Completed attempts</b> {len(rows)} / {esc(manifest["planned_trials"])}</span>
<span><b>Order seed</b> {esc(manifest["seed"])}</span></div>
<p class="completion">{esc(completeness)}</p>
<section aria-labelledby="comparison-title">
<div class="section-title"><h2 id="comparison-title">Condition comparison</h2>
<span>Pass = every contract test passes</span></div>
<div class="table-scroll"><table>
<thead><tr><th>Instruction condition</th><th>Passed / attempted</th><th>Other outcomes</th>
<th>Median model time</th><th>Reported tokens</th><th>Paired with baseline</th></tr></thead>
<tbody>{"".join(summary_rows)}</tbody></table></div>
<p class="caption">Tokens = input + output; cached input is already included in input.
Missing usage stays unknown. Errors and timeouts remain in attempted counts.
Paired wins/losses use only pairs with completed test outcomes.
This is an observed comparison, not a significance test.</p>
</section>
<section aria-labelledby="matrix-title">
<div class="section-title"><h2 id="matrix-title">Inspect each repeat</h2>
<span>Select an outcome to see its evidence</span></div>
<div class="table-scroll"><table class="matrix"><thead><tr><th>Repair task</th>
{"".join("<th>" + esc(v["label"]) + "</th>" for v in manifest["variants"])}</tr></thead>
<tbody>{"".join(matrix)}</tbody></table></div>
</section>
<section aria-labelledby="evidence-title">
<div class="section-title"><h2 id="evidence-title">Trial evidence</h2>
<label>Show <select id="filter"><option value="all">All outcomes</option>
<option value="failed">Failed tests</option><option value="passed">Passed tests</option>
<option value="error">Runner errors</option>
<option value="timeout">Timeouts</option></select></label></div>
<p id="empty" hidden>No trials match this filter.</p>
{"".join(details) or "<p>No trials completed. Inspect the manifest and runner setup.</p>"}
</section>
<details class="method"><summary>Method, provenance &amp; limits</summary>
<p>SKILL.md text is injected into the task prompt. Native discovery and supporting scripts
are not evaluated. Codex configuration is inherited; global instructions can affect all conditions.
Tasks are single-module Python repairs from the selected task pack. Neither task secrecy
nor resistance to grader manipulation is claimed. Only use trusted task packs and skills.</p>
<p>Repeated task IDs are paired, but model calls are independent. The order seed shuffles
execution; it does not make model output deterministic. Inspect the original run folder
before sharing: prompts and logs can contain private skill text.</p>
<pre>{esc(json.dumps(manifest, indent=2, ensure_ascii=False))}</pre>
</details>
</main><footer>Skill Compare Lab {esc(manifest["tool_version"])} · Offline report ·
{esc(manifest["created_at"])}</footer>
<script>
const filter = document.getElementById('filter');
const evidence = Array.from(document.querySelectorAll('.evidence'));
filter.addEventListener('change', () => {{
  evidence.forEach(item => {{
    item.hidden = filter.value !== 'all' && item.dataset.status !== filter.value;
  }});
  document.getElementById('empty').hidden = evidence.some(item => !item.hidden);
}});
function revealTrial() {{
  const item = document.getElementById(location.hash.slice(1));
  if (item && item.classList.contains('evidence')) {{
    filter.value = 'all'; filter.dispatchEvent(new Event('change')); item.open = true;
    item.scrollIntoView({{block: 'start'}});
  }}
}}
window.addEventListener('hashchange', revealTrial);
revealTrial();
</script></body></html>
"""
    path = directory / "report.html"
    path.write_text(document, encoding="utf-8")
    return path
