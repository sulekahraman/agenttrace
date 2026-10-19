"""Build the saved session-replay report; never invoke a model provider."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import runpy
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = ROOT / "data/programbench-pr10"
SCOUT_CLASSES = ("duplicated_work", "weak_handoff", "unintegrated_information")
COMM_CLASSES = ("disclosure", "delivery", "reading", "action")


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assemble(work: Path, viewer: Path, viewer_base: str):
    from agenttrace.communication.evidence import digest
    from agenttrace.models import AnalysisRun, Analyzer, Provenance
    from agenttrace.store import Store

    manifest = read(work / "manifest.json")
    agents = read(work / "agents.json")
    harness = runpy.run_path(str(work / "replay.py"))
    store = Store(viewer)
    rows = []
    completed = datetime.now(timezone.utc).isoformat()
    for source in manifest["rows"]:
        slug = source["slug"]
        directory = work / slug
        asyncio.run(harness["scout"](slug))
        asyncio.run(harness["communication"](slug))
        report = read(directory / "report.input.json")
        existing = {
            run["analyzer"]["name"]: run for run in store.list_runs(source["trace_id"])
            if run["status"] == "completed" and run["analyzer"]["kind"] == "offline"
        }
        records = {}
        for key, name, version, prompt in (
            ("scout", "scout_collaboration_v1", "2.2.0", "8"),
            ("communication", "communication_failures_v1", "0.1.0", "1"),
        ):
            output = read(directory / f"{key}.result.json")
            roles = ("scout",) if key == "scout" else ("A", "B", "judge")
            selected_agents = {role: agents[slug][role] for role in roles}
            output["session_replay"] = {
                "surface": manifest["execution"],
                "requested_model": "gpt-6.1-sol",
                "agents": selected_agents,
                "direct_provider_api_calls": 0,
                "caveat": (
                    "Scout targets and collaboration share context; batches may expose nearby later targets. Not independent native calls."
                    if key == "scout" else
                    "A, B and judge use separate session-agent contexts; not native provider calls."
                ),
            }
            provenance = Provenance(
                completed_at=completed, model=manifest["model"], prompt_version=prompt,
                taxonomy_version="communication-transitions/1" if key == "communication" else None,
                evidence_sha256=source["evidence_sha256"] if key == "communication" else None,
                configuration_sha256=digest({
                    "analyzer": name, "version": version, "prompt_version": prompt,
                    "model": manifest["model"], "execution": manifest["execution"],
                    "evidence_sha256": source["evidence_sha256"],
                }),
            )
            record = AnalysisRun(
                id=f"run_sol12_{slug}_{key}", trace_id=source["trace_id"],
                analyzer=Analyzer(name=name, version=version, kind="pipeline"),
                status="completed", provenance=provenance, output=output,
            ).record()
            store.save_run(record)
            records[key] = record
        rows.append({
            "slug": slug, "trace_id": source["trace_id"],
            "agenttrace_url": viewer_base + "/?" + urlencode({"trace": source["trace_id"]}),
            "metrics": report["metrics"], "structural_flags": report["failureModes"],
            "offline_analyses": existing, **records,
            "input": source,
            "replay_sha256": {
                filename: sha(directory / filename) for filename in (
                    "annotations.reply.json", "collaboration.reply.json",
                    "A.reply.json", "B.reply.json", "judge.reply.json",
                )
            },
            "prompt_sha256": {
                filename: sha(directory / filename) for filename in (
                    "collaboration.prompt.txt", "A.prompt.txt", "B.prompt.txt", "judge.prompt.txt",
                )
            },
        })
    result = {
        "schema": "agenttrace/sol12-session-replay-report.v1",
        "completed_at": completed, "model": manifest["model"],
        "execution": manifest["execution"], "direct_provider_api_calls": 0,
        "source_commit": "913ad1805642a38e5248d67e5d8c3b83c48b51b5",
        "source_code_sha256": {
            str(path.relative_to(ROOT)): sha(path) for path in [
                ROOT / "packages/agenttrace-api/agenttrace/scout/scanners.py",
                ROOT / "packages/agenttrace-api/agenttrace/scout/annotations.py",
                ROOT / "packages/agenttrace-api/agenttrace/scout/adapter.py",
                ROOT / "packages/agenttrace-api/agenttrace/communication/analysis.py",
                ROOT / "packages/agenttrace-api/agenttrace/communication/evidence.py",
            ]
        },
        "caveats": [
            "Session prompt replay, not a native Inspect/provider execution or a controlled model comparison.",
            "Scout targets share per-trace context; chronological batches may expose nearby later targets.",
            "Scout collaboration candidates are regenerated from the new labels, not held at baseline.",
            "Communication A, B and judge are separate session agents using the current evidence caps.",
            "Outputs pass current native structural validators; this does not establish semantic accuracy.",
            "No independent human labels, hidden-test grades, full model inputs or workspace history.",
            "Offline detector results are preserved from the frozen baseline, not new model judgments.",
        ],
        "runs": rows,
    }
    write(HERE / "results.json", result)
    return result


def restore(results, destination):
    from agenttrace.communication.evidence import build_evidence
    from agenttrace.store import Store

    if destination.exists():
        raise ValueError("Restore destination must not exist.")
    destination.mkdir(parents=True)
    with sqlite3.connect(f"file:{BASELINE}/agenttrace.sqlite3?mode=ro", uri=True) as source:
        with sqlite3.connect(destination / "agenttrace.sqlite3") as target:
            source.backup(target)
    store = Store(destination)
    for row in results["runs"]:
        task, suffix = row["slug"].split("-", 1)
        trace = store.get_trace(row["trace_id"])
        evidence = build_evidence(trace, BASELINE / "sources" / f"{task}-2026-10-15" / suffix / "record-run")
        if evidence["sha256"] != row["input"]["evidence_sha256"]:
            raise ValueError(f"Restored evidence hash mismatch: {row['slug']}")
        store.save_evidence(row["trace_id"], evidence)
        for key in ("scout", "communication"):
            store.save_run(row[key])


def render(results):
    rows = results["runs"]
    if len(rows) != 12 or sum(r["input"]["messages"] for r in rows) != 602:
        raise ValueError("Expected the complete 12-run, 602-agent-message cohort.")
    scout_counts = Counter()
    communication_counts = {key: Counter() for key in COMM_CLASSES}
    supported = Counter()
    unresolved = 0
    table = []
    for row in rows:
        findings = {f["category"]: f for f in row["scout"]["output"]["findings"]}
        classes = {c["failure_class"]: c for c in row["communication"]["output"]["classes"]}
        if set(findings) != set(SCOUT_CLASSES) or set(classes) != set(COMM_CLASSES):
            raise ValueError(f"Incomplete metrics: {row['slug']}")
        for key, finding in findings.items():
            scout_counts[key] += finding["found"]
        for key, assessment in classes.items():
            communication_counts[key][assessment["status"]] += 1
        for incident in row["communication"]["output"]["incidents"]:
            if incident["status"] == "supported":
                supported[incident["failure_class"]] += 1
            else:
                unresolved += 1
        cells = [f'<td><a target="_blank" rel="noopener" href="{html.escape(row["agenttrace_url"], quote=True)}">{html.escape(row["slug"])}</a></td>',
                 f'<td>{row["input"]["messages"]}</td>']
        for key in SCOUT_CLASSES:
            value = findings[key]["found"]
            cells.append(f'<td class="{"positive" if value else "negative"}">{"Yes" if value else "No"}</td>')
        for key in COMM_CLASSES:
            value = classes[key]["status"]
            label = {"supported_failure": "Yes", "no_failure_found": "No", "undecidable": "Unknown", "not_applicable": "N/A"}[value]
            style = {"supported_failure": "positive", "no_failure_found": "negative", "undecidable": "unknown", "not_applicable": ""}[value]
            cells.append(f'<td class="{style}" title="{html.escape(classes[key]["explanation"], quote=True)}">{label}</td>')
        table.append("<tr>" + "".join(cells) + "</tr>")
    counts = ", ".join(
        f'{name}: <strong>{scout_counts[key]}/12</strong>' for key, name in zip(
            SCOUT_CLASSES, ("duplicated work", "weak handoff", "unintegrated information")
        )
    )
    comm = "; ".join(
        f'{key}: <strong>{communication_counts[key]["supported_failure"]}/12 supported</strong>, '
        f'{communication_counts[key]["undecidable"]}/12 unknown'
        for key in COMM_CLASSES
    )
    incident_count = sum(supported.values())
    shortened = sum(len(row["communication"]["output"]["coverage"]["truncated_events"]) for row in rows)
    omitted = sum(len(row["communication"]["output"]["coverage"]["omitted_events"]) for row in rows)
    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>12-run results: latest Scout + communication failures</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1250px;margin:35px auto;padding:0 24px;color:#17283b;background:#f7f9fc}}
h1{{font-size:27px;margin-bottom:4px}}p{{margin:10px 0}}a{{color:#135fb1}}.meta{{color:#556575}}
.card{{background:white;border:1px solid #dbe3ee;border-radius:10px;padding:16px 20px;margin:18px 0}}
table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:9px 7px;text-align:left;border-bottom:1px solid #e3e8ef}}
th{{background:#eef3f9}}.positive{{color:#a32821;font-weight:650}}.negative{{color:#37556a}}.unknown{{color:#886015;font-weight:600}}
.scroll{{overflow-x:auto}}small{{font-size:12px}}@media print{{body{{margin:0;background:white;font-size:12px}}.card{{break-inside:avoid}}@page{{size:A4 landscape;margin:12mm}}}}
</style>
<h1>Latest rubrics: 12 ProgramBench runs</h1>
<p class="meta">GPT-6.1 Sol session replay &middot; 602 agent posts &middot; Scout 2.2.0 / prompt 8 &middot;
communication 0.1.0 / prompt 1 &middot; no direct provider API calls</p>
<div class="card"><p><strong>Scout:</strong> {counts}.</p>
<p><strong>Communication:</strong> {comm}.</p>
<p>{incident_count} supported incidents (first failed transition only); {unresolved} retained undecidable candidates.
Repair does not erase an evidenced failure.</p></div>
<div class="card scroll"><table><thead><tr><th>Run / AgentTrace visualization</th><th>Posts</th>
<th>Duplicated<br>work</th><th>Weak<br>handoff</th><th>Unintegrated<br>information</th>
<th>Disclosure</th><th>Delivery</th><th>Reading</th><th>Action</th></tr></thead>
<tbody>{''.join(table)}</tbody></table>
<p><small>Each run link opens its saved results and communication visualizations in the local AgentTrace UI.
Yes = model-supported positive; No = no qualifying evidence in the assessed scope, not proof of absence.
Unknown is not a negative. Hover over communication cells for explanations.</small></p></div>
<p><strong>Interpretation:</strong> the October 17 baseline flagged all 12 runs in each Scout category.
This rerun changes model, rubric and candidate labels; lower flag counts do not establish better accuracy.
Missing delivered context/workspace history and clipped execution evidence ({shortened} events shortened;
{omitted} omitted) limit causal attribution.</p>
<p><small><strong>Method:</strong> Scout labels share per-trace context (including nearby later targets in a batch); communication A/B/judge use
separate sessions. Current native validators check outputs, but this is not native provider inference or human gold.
Your OpenAI API key was not used; Copilot session usage is separate.
Offline structural/regex/facts results are preserved, available with complete metrics in the UI and
<a href="results.json">full results/provenance JSON</a>. <a href="README.md">Method and viewer restore</a>.</small></p>
</html>"""
    (HERE / "index.html").write_text(page)
    write(HERE / "summary.json", {
        "runs": len(rows), "agent_messages": 602, "direct_provider_api_calls": 0,
        "scout_positive_runs": dict(scout_counts),
        "communication_class_statuses": {key: dict(value) for key, value in communication_counts.items()},
        "supported_incidents": dict(supported), "undecidable_candidates": unresolved,
        "evidence_shortened_events": shortened, "evidence_omitted_events": omitted,
        "visualizations": [{"run": row["slug"], "url": row["agenttrace_url"]} for row in rows],
    })
    print(json.dumps(read(HERE / "summary.json"), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--viewer", type=Path, default=ROOT / ".agenttrace/sol-12-runs-2026-10-19")
    parser.add_argument("--viewer-base", default="http://127.0.0.1:3012")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    origin = urlsplit(args.viewer_base)
    if origin.scheme != "http" or origin.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError("Viewer links must target a local HTTP origin.")
    results = assemble(args.work.resolve(), args.viewer, args.viewer_base.rstrip("/")) if args.work else read(HERE / "results.json")
    if args.restore:
        restore(results, args.restore)
    render(results)


if __name__ == "__main__":
    main()
