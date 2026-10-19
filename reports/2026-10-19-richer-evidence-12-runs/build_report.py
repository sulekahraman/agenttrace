"""Persist and render completed richer-evidence session judgments; no provider calls."""
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
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = ROOT / "reports/2026-10-19-sol-12-runs"
COMMUNICATION = ("disclosure", "delivery", "reading", "action")
SCOUT = ("duplicated_work", "weak_handoff", "unintegrated_information")
METRIC_NAMES = {
    "duplicated_work": "Duplicated work",
    "weak_handoff": "Weak handoff",
    "unintegrated_information": "Unintegrated information",
    "disclosure": "Disclosure failure",
    "delivery": "Delivery failure",
    "reading": "Reading failure",
    "action": "Action failure",
}
CLASS_LABELS = {
    "supported_failure": "Yes - failure flagged",
    "no_failure_found": "No - no qualifying failure found",
    "undecidable": "Unknown - cannot determine",
    "not_applicable": "N/A - solo run",
}
STATUS_CSS = {
    "supported_failure": "positive", "no_failure_found": "negative",
    "undecidable": "muted", "not_applicable": "muted",
}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assemble(work, viewer, viewer_base):
    from agenttrace.communication.evidence import digest
    from agenttrace.models import AnalysisRun, Analyzer, Provenance
    from agenttrace.store import Store

    manifest = read(work / "manifest.json")
    for filename, expected in manifest["source_code_sha256"].items():
        if sha(ROOT / filename) != expected:
            raise ValueError(f"Frozen replay implementation changed: {filename}")
    agents = read(work / "agents.json")
    assert len({identifier for roles in agents.values() for identifier in roles.values()}) == 36
    previous = {row["slug"]: row for row in read(PREVIOUS / "results.json")["runs"]}
    harness = runpy.run_path(str(work / "replay.py"))
    store = Store(viewer)
    completed = datetime.now(timezone.utc).isoformat()
    rows = []
    for item in manifest["rows"]:
        slug = item["slug"]
        directory = work / slug
        assert set(agents[slug]) == {"A", "B", "judge"}
        asyncio.run(harness["communication"](slug))
        baseline = previous[slug]
        assert store.get_run(baseline["scout"]["id"]) == baseline["scout"]
        output = read(directory / "communication.result.json")
        assert output["evidence_sha256"] == item["evidence_sha256"]
        assert all(
            event_id.startswith("detail:") for key in ("omitted_events", "truncated_events")
            for event_id in output["coverage"][key]
        )
        output["session_replay"] = {
            "surface": manifest["execution"], "requested_model": "gpt-6.1-sol",
            "agents": agents[slug], "direct_provider_api_calls": 0,
            "caveat": "A, B and judge use separate session-agent contexts, not native provider calls.",
        }
        run = AnalysisRun(
            id=f"run_rich12_{slug}_communication", trace_id=item["trace_id"],
            analyzer=Analyzer(
                name="communication_failures_v1", version=manifest["communication_version"], kind="pipeline",
            ),
            status="completed",
            provenance=Provenance(
                completed_at=completed, model=manifest["model"],
                prompt_version=manifest["communication_prompt_version"],
                taxonomy_version="communication-transitions/1", evidence_sha256=item["evidence_sha256"],
                configuration_sha256=digest({
                    "version": manifest["communication_version"],
                    "prompt_version": manifest["communication_prompt_version"],
                    "model": manifest["model"], "execution": manifest["execution"],
                    "source_commit": manifest["source_commit"],
                    "evidence_sha256": item["evidence_sha256"],
                    "rubric_sha256": manifest["rubric_sha256"],
                }),
            ),
            output=output,
        ).record()
        store.save_run(run)
        rows.append({
            "slug": slug, "trace_id": item["trace_id"],
            "agenttrace_url": viewer_base + "/?" + urlencode({"trace": item["trace_id"], "analysis": run["id"]}),
            "metrics": baseline["metrics"], "structural_flags": baseline["structural_flags"],
            "offline_analyses": baseline["offline_analyses"],
            "scout": baseline["scout"], "previous_communication": baseline["communication"],
            "communication": run, "input": item,
            "replay_sha256": {f"{tag}.reply.json": sha(directory / f"{tag}.reply.json") for tag in ("A", "B", "judge")},
            "prompt_sha256": {f"{tag}.prompt.txt": sha(directory / f"{tag}.prompt.txt") for tag in ("A", "B", "judge")},
        })
    result = {
        "schema": "agenttrace/richer-evidence-session-report.v1", "completed_at": completed,
        "model": manifest["model"], "execution": manifest["execution"], "direct_provider_api_calls": 0,
        "source_commit": manifest["source_commit"], "source_code_sha256": manifest["source_code_sha256"],
        "rubric_sha256": manifest["rubric_sha256"],
        "scout": manifest["scout"],
        "caveats": [
            "Communication rerun: 12 independent A/B pairs and 12 independent judges; session prompt replay, not native provider generation.",
            "Scout's 602 annotations and three flags are unchanged from the previous session report; targets shared per-trace context.",
            "Every core summary event is supplied without additional clipping; long commands/outputs are summarized, and full-detail supplements remain explicitly clipped/omitted.",
            "Recorded prompts and tool outputs are not complete serialized model API requests.",
            "Workspace snapshots cover second-resolution message batches; concurrent shell-write attribution remains limited.",
            "A receipt does not prove understanding. Unknown does not mean negative, and repair does not erase failure.",
            "Structural/citation validation is not human-gold semantic accuracy. No controlled causal model comparison.",
            "Previous-versus-new changes mix additional evidence, rubric version and sampling; not an accuracy improvement measurement.",
        ],
        "runs": rows,
    }
    write(HERE / "results.json", result)
    return result


def summarize(result):
    rows = result["runs"]
    classes = {
        name: dict(Counter(
            item["status"] for row in rows for item in row["communication"]["output"]["classes"]
            if item["failure_class"] == name
        )) for name in COMMUNICATION
    }
    previous = {
        name: dict(Counter(
            item["status"] for row in rows for item in row["previous_communication"]["output"]["classes"]
            if item["failure_class"] == name
        )) for name in COMMUNICATION
    }
    supported = Counter(
        incident["failure_class"] for row in rows for incident in row["communication"]["output"]["incidents"]
        if incident["status"] == "supported"
    )
    return {
        "runs": len(rows), "agent_messages": sum(len(row["scout"]["output"]["annotations"]) for row in rows),
        "direct_provider_api_calls": 0, "independent_session_stages": 36,
        "scout_rerun": False,
        "scout_positive_runs": {
            name: sum(any(f["category"] == name and f["found"] for f in row["scout"]["output"]["findings"]) for row in rows)
            for name in SCOUT
        },
        "communication_class_statuses": classes, "previous_communication_class_statuses": previous,
        "supported_incidents": {name: supported[name] for name in COMMUNICATION},
        "undecidable_incidents": sum(
            incident["status"] == "undecidable" for row in rows for incident in row["communication"]["output"]["incidents"]
        ),
        "core_events_omitted": 0, "core_events_clipped": 0,
        "detail_events_omitted": sum(len(row["communication"]["output"]["coverage"]["omitted_events"]) for row in rows),
        "detail_events_clipped": sum(len(row["communication"]["output"]["coverage"]["truncated_events"]) for row in rows),
        "capture": {
            "recorded_inputs": sum(event["kind"] == "input" for row in rows for event in row["communication"]["output"]["evidence"]),
            "native_actions": sum(event["id"].startswith("action:") for row in rows for event in row["communication"]["output"]["evidence"]),
            "native_sessions": sum(len(row["communication"]["output"]["coverage"]["agents"]) for row in rows),
            "workspace_snapshots": sum(
                event["id"].startswith("workspace:") and event["id"] != "workspace:manifest"
                for row in rows for event in row["communication"]["output"]["evidence"]
            ),
        },
        "visualizations": [{"run": row["slug"], "url": row["agenttrace_url"]} for row in rows],
    }


def render(result):
    summary = summarize(result)
    assert summary["capture"] == {
        "recorded_inputs": 195, "native_actions": 2322, "native_sessions": 36, "workspace_snapshots": 174,
    }
    write(HERE / "summary.json", summary)
    escape = html.escape
    totals = []
    for name in COMMUNICATION:
        counts = summary["communication_class_statuses"][name]
        old = summary["previous_communication_class_statuses"][name].get("supported_failure", 0)
        totals.append(
            f'<tr><th><a href="#metric-{name}">{METRIC_NAMES[name]}</a></th><td>{old}/12</td><td>{counts.get("supported_failure", 0)}/12</td>'
            f"<td>{counts.get('no_failure_found', 0)}/12</td><td>{counts.get('undecidable', 0)}/12</td></tr>"
        )
    scout_table, communication_table, details = [], [], []
    for row in result["runs"]:
        output = row["communication"]["output"]
        flags = {finding["category"]: finding["found"] for finding in row["scout"]["output"]["findings"]}
        run_cell = f'<th scope="row"><a href="{escape(row["agenttrace_url"], quote=True)}">{escape(row["slug"])}</a></th>'
        scout_cells = [
            f'<td class="{"positive" if flags[name] else "muted"}">{"Yes - flagged" if flags[name] else "No - not flagged"}</td>'
            for name in SCOUT
        ]
        scout_table.append("<tr>" + run_cell + "".join(scout_cells) + "</tr>")
        cells = [run_cell]
        for item in sorted(output["classes"], key=lambda item: COMMUNICATION.index(item["failure_class"])):
            status = item["status"]
            cells.append(f'<td class="{STATUS_CSS[status]}" title="{escape(item["explanation"], quote=True)}">{CLASS_LABELS[status]}</td>')
        communication_table.append("<tr>" + "".join(cells) + "</tr>")
        supported = sum(incident["status"] == "supported" for incident in output["incidents"])
        unresolved = sum(incident["status"] == "undecidable" for incident in output["incidents"])
        incident_text = "".join(
            f'<li><b>{"Failure flagged: " + METRIC_NAMES[incident["failure_class"]] if incident["status"] == "supported" else "Unresolved candidate (not counted as a flagged failure)"}'
            f': {escape(incident["work_item"])}</b>'
            f'<p>{escape(incident["consequence"])}</p><small>Recovery: {escape(incident["recovery"]["status"])}. '
            f'Anchor: {escape(incident["anchor"])}; dependent event: {escape(incident["dependent_event"])}.</small></li>'
            for incident in output["incidents"]
        )
        assessments = "".join(
            f'<p><b>{METRIC_NAMES[item["failure_class"]]} - {CLASS_LABELS[item["status"]]}:</b> {escape(item["explanation"])}</p>'
            for item in output["classes"]
        )
        audit_rows = []
        for name in COMMUNICATION:
            judgments = [
                next(item for item in assessment["classes"] if item["failure_class"] == name)
                for assessment in (output["annotations"]["A"], output["annotations"]["B"], output)
            ]
            audit_rows.append(
                f"<tr><th>{METRIC_NAMES[name]}</th>" + "".join(
                    f'<td class="{STATUS_CSS[item["status"]]}">{CLASS_LABELS[item["status"]]}</td>'
                    for item in judgments
                ) + "</tr>"
            )
        candidates = {
            f"{role}:{incident['id']}": incident
            for role in ("A", "B") for incident in output["annotations"][role]["incidents"]
        }
        decisions = "".join(
            f'<tr><th>{escape(decision["candidate_id"])}</th>'
            f'<td>{"Failure flagged: " + METRIC_NAMES[candidates[decision["candidate_id"]]["failure_class"]] if candidates[decision["candidate_id"]]["status"] == "supported" else "Unresolved candidate"}</td>'
            f'<td>{"Retained as " + escape(decision["final_incident_id"]) if decision["decision"] == "kept" else "Rejected - not retained"}</td>'
            f'<td>{escape(decision["reason"])}</td></tr>'
            for decision in output["decisions"]
        )
        details.append(
            f'<details id="findings-{escape(row["slug"], quote=True)}"><summary>{escape(row["slug"])}: '
            f'{supported} flagged failure incident(s), {unresolved} unresolved candidate(s)</summary>'
            "<h3>Who flagged each failure type?</h3>"
            '<div class="scroll"><table><thead><tr><th>Failure type</th><th>Independent annotator A</th>'
            "<th>Independent annotator B</th><th>Final model adjudicator (reported above)</th></tr></thead><tbody>"
            + "".join(audit_rows) + "</tbody></table></div>"
            f'<p>{escape(output["explanation"])}</p><h3>Final retained incidents and unresolved candidates</h3>'
            f'<ul>{incident_text}</ul>{assessments}'
            "<h3>Which A/B candidate incidents did the final adjudicator retain?</h3>"
            "<p>A retained candidate can still be unresolved; only final supported incidents count as flagged failures. "
            "Duplicate candidates can be merged into one final incident.</p>"
            '<div class="scroll"><table><thead><tr><th>Proposing annotator: candidate ID</th><th>Annotator proposal</th>'
            "<th>Final adjudicator decision</th><th>Reason for retaining or rejecting</th></tr></thead><tbody>"
            + decisions + "</tbody></table></div></details>"
        )
    incidents = ", ".join(f"{name}: {summary['supported_incidents'][name]}" for name in COMMUNICATION)
    page = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentTrace: richer evidence, 12 runs</title>
<style>
body{font:15px/1.55 system-ui,sans-serif;max-width:1160px;margin:40px auto;padding:0 22px;color:#19242e;background:#fafbfc}
h1{line-height:1.2}a{color:#0755a1}table{border-collapse:collapse;width:100%;margin:18px 0;background:white}
th,td{text-align:left;vertical-align:top;padding:9px 11px;border-bottom:1px solid #dfe5eb}thead{background:#eef2f7}
.scroll{overflow:auto}.positive{color:#a22425;font-weight:650}.negative{color:#176b44}.muted,small{color:#526273}
.note{padding:15px 18px;border-left:4px solid #4c78a8;background:#eef4fa}
details{border-top:1px solid #dfe5eb;padding:12px 0}summary{cursor:pointer;font-weight:650}
code{background:#edf0f3;padding:1px 4px}li p{margin:5px 0}h2{margin-top:32px}
</style><main>
<h1>Richer evidence: 12-run reassessment</h1>
<p class="muted">October 19, 2026 · GPT-6.1 Sol session agents · communication v0.2.0 / prompt 2 · no direct provider API calls</p>
"""
    page += (
        f"<p><b>Final model-adjudicated failure incidents (not runs):</b> {escape(incidents)}. "
        f"<b>{summary['undecidable_incidents']} unresolved candidate incidents</b> are retained separately, "
        "not counted as flagged failures. These are model judgments, not verified ground truth.</p>"
        "<h2>How to read the decisions</h2>"
        "<p><b>Scout:</b> the prior Scout analysis returned one binary failure flag per metric per run. "
        "<b>Communication:</b> independent annotators A and B proposed incidents; a separate model adjudicator "
        "reviewed both against the evidence, rejected or merged candidates, and made the final decisions shown in the tables. "
        "A flag from either annotator alone is <b>not</b> a final positive. Expand a run below to see A, B and the final decision side by side.</p>"
        '<div class="scroll"><table id="decision-legend"><thead><tr><th>Report label / saved status</th>'
        "<th>Was a failure flagged in the final result?</th><th>Meaning</th></tr></thead><tbody>"
        "<tr><th>Yes - failure flagged<br><code>supported_failure</code> / incident <code>supported</code></th>"
        "<td>Yes</td><td>The final adjudicator retained at least one evidence-supported incident of this failure type. "
        "This is not just agreement between annotators and is not proof of model accuracy.</td></tr>"
        "<tr><th>No - no qualifying failure found<br><code>no_failure_found</code></th><td>No</td>"
        "<td>The adjudicator could assess this type within the supplied evidence and found no qualifying incident. "
        "This is a scoped negative result, not proof that no failure occurred anywhere.</td></tr>"
        "<tr><th>Unknown - cannot determine<br><code>undecidable</code></th><td>Neither yes nor no</td>"
        "<td>The evidence does not establish whether a qualifying failure occurred or where it belongs. "
        "This is an abstention, not a negative flag; an annotator may still have proposed a candidate.</td></tr>"
        "<tr><th>N/A - solo run<br><code>not_applicable</code> at run/type level</th><td>Not applicable</td>"
        "<td>Fewer than two agent participants, so inter-agent failure assessment does not apply. "
        "None of these 12 runs is solo. Missing evidence is Unknown, not N/A.</td></tr>"
        "<tr><th>Scout: Yes - flagged / No - not flagged<br><code>found=true</code> / <code>found=false</code></th>"
        "<td>Yes / No, respectively</td><td>The saved Scout finding is a binary decision. "
        "Scout has no separate Unknown output; a No does not guarantee complete evidence or absence of failure.</td></tr>"
        "<tr><th>Unsupported / rejected candidate<br>adjudication <code>rejected</code></th>"
        "<td>That candidate did not become a final retained incident</td>"
        "<td>An annotator proposed it, but the adjudicator rejected it with a reason. "
        "This is <b>not</b> a run-level metric status: the final type may be Unknown, No, or Yes because of another incident.</td></tr>"
        "</tbody></table></div>"
        "<p><b>Other saved labels:</b> within a single incident, transition <code>passed</code> means that communication step succeeded "
        "(not that a failure was flagged); <code>failed</code> means that step failed; <code>unknown</code> means unresolved evidence; "
        "<code>not_applicable</code> can mark downstream steps not assessed after an earlier failure. "
        "Recovery <code>repaired</code>, <code>unresolved</code> or <code>unknown</code> describes what happened later. "
        "<b>A repaired failure still counts as a failure.</b></p>"
        "<h2>What each of the seven metrics means</h2>"
        "<p>These are failure-detection judgments, not task-success scores, severity scores or calibrated probabilities.</p>"
        "<table><thead><tr><th>Metric</th><th>What a Yes means</th></tr></thead><tbody>"
        '<tr id="metric-duplicated_work"><th>Scout: duplicated work</th><td>Different agents repeated materially equivalent '
        "analysis or execution without a useful verification, synthesis, handoff or corrective-rework purpose. "
        "Repeated status updates or requested independent checks do not qualify.</td></tr>"
        '<tr id="metric-weak_handoff"><th>Scout: weak handoff</th><td>A concrete request or commitment was abandoned, '
        "a result was not delivered or integrated, or conflicting ownership caused observable coordination failure. "
        "Silence or a missing acknowledgement alone does not qualify.</td></tr>"
        '<tr id="metric-unintegrated_information"><th>Scout: unintegrated information</th><td>A later dependent decision or action '
        "ignored, contradicted without addressing, or omitted relevant shared information despite positive evidence of an opportunity "
        "to use it. Publication order alone and reasoned rejection do not qualify.</td></tr>"
        '<tr id="metric-disclosure"><th>Communication: disclosure failure</th><td>An agent held relevant information but did not '
        "share it clearly, accurately and in time when sharing was needed. A missing chat mention alone is insufficient.</td></tr>"
        '<tr id="metric-delivery"><th>Communication: delivery failure</th><td>Information was clearly shared in time but did not '
        "reach the recipient before the affected action. Publication or native command stdout alone does not prove receipt.</td></tr>"
        '<tr id="metric-reading"><th>Communication: reading failure</th><td>A clear message reached the recipient, '
        "but the recipient misinterpreted or forgot it. Evidence of the recipient's expressed account is required; receipt alone is insufficient.</td></tr>"
        '<tr id="metric-action"><th>Communication: action failure</th><td>The recipient received and correctly understood '
        "a commitment, but subsequent execution violated it. An ordinary coding or calculation error alone does not qualify.</td></tr>"
        "</tbody></table>"
        '<p>Definitions: <a href="../../packages/agenttrace-api/agenttrace/scout/scanners.py">Scout rubric '
        "(analyze_collaboration)</a>; "
        '<a href="../../packages/agenttrace-api/agenttrace/communication/analysis.py">communication rubric, '
        "status schema and validation (RUBRIC / ClassAssessment / Incident)</a>.</p>"
        "<p>Communication follows <b>disclosure → delivery → reading → action</b>. "
        "An incident is assigned only its first evidenced failed step; earlier steps must be established as successful "
        "before a later step can be blamed. Scout's broader collaboration flags are separate assessments, not a one-to-one mapping to these steps.</p>"
        '<div class="note" id="sharing"><b>Sharing this report:</b> send or download this HTML file and open it in a browser; '
        "the tables, definitions and expandable findings need no server. Include the report folder for the saved JSON judgments. "
        "<b>Visualization links use 127.0.0.1:3013 and will not connect teammates to the author's computer.</b> "
        "Interactive charts require a shared viewer or each teammate's own restored local viewer. "
        "Source-code, documentation and previous-report links require the surrounding repository.</div>"
        "<h2>Communication comparison: how many of the 12 runs had each final decision?</h2>"
        "<p><b>Every cell below counts runs, not incidents.</b> For example, 6/12 delivery failures means the final adjudicator "
        "flagged at least one delivery incident in six runs; those runs contain seven delivery incidents in total. "
        "For each type, the three richer-evidence columns sum to 12. A run can contain several incidents or failure types. "
        "The earlier and richer-evidence analyses used different evidence/rubrics, so this is not an accuracy comparison.</p>"
        '<div class="scroll"><table id="communication-totals"><thead><tr><th>Communication failure type</th>'
        "<th>Earlier analysis: runs with a failure flagged</th><th>Richer evidence: runs with a failure flagged</th>"
        "<th>Richer evidence: runs with no qualifying failure found</th><th>Richer evidence: runs with inconclusive evidence</th></tr></thead><tbody>"
        + "".join(totals) + "</tbody></table>"
        "</div><h2>Per-run Scout results: three binary failure flags</h2>"
        "<p>Each row is one run. <b>These are prior Scout decisions, carried over unchanged, not rerun with the richer evidence.</b> "
        "Run names open the saved read-only AgentTrace visualization, pinned to the richer communication analysis.</p>"
        '<div class="scroll"><table id="scout-results"><thead><tr><th>Run / open AgentTrace visualization</th>'
        '<th><a href="#metric-duplicated_work">Duplicated work flagged?</a></th>'
        '<th><a href="#metric-weak_handoff">Weak handoff flagged?</a></th>'
        '<th><a href="#metric-unintegrated_information">Unintegrated information flagged?</a></th></tr></thead><tbody>'
        + "".join(scout_table) + "</tbody></table></div>"
        "<h2>Per-run communication results: final adjudicator decisions</h2>"
        "<p>Each cell answers whether the final model adjudicator flagged this failure type in this run. "
        "<b>Unknown is not No.</b> Hover for the reasoning, or expand the corresponding run below for annotator A/B decisions and explanations.</p>"
        '<div class="scroll"><table id="communication-results"><thead><tr><th>Run / open AgentTrace visualization</th>'
        + "".join(f'<th><a href="#metric-{name}">{METRIC_NAMES[name]} flagged?</a></th>' for name in COMMUNICATION)
        + "</tr></thead><tbody>" + "".join(communication_table) + "</tbody></table></div>"
        "<div class=\"note\"><b>What changed:</b> 195 recorded inputs, 2,322 timed actions, 36 native sessions and 174 workspace snapshots, "
        "validated against the pinned source. Receipt now uses model-visible outputs, not native stdout alone. "
        f"Every core summary is included; long commands/outputs are summarized. {summary['detail_events_clipped']} supplemental events are shortened and "
        f"{summary['detail_events_omitted']} omitted. Full serialized API requests and per-action workspace attribution remain unavailable.</div>"
        "<p class=\"muted\">36 independent session stages: A, B and adjudicator for each run. Automated judgments, not human-gold accuracy. "
        "The comparison changes evidence, rubric and sampling; it does not measure model improvement. "
        "Scout's prior session-context limitations still apply.</p>"
        "<p><a href=\"results.json\">Complete judgments, citations &amp; provenance</a> · "
        "<a href=\"summary.json\">Machine-readable summary</a> · "
        "<a href=\"../../docs/communication-evidence.md\">Evidence limits</a> · "
        "<a href=\"../2026-10-19-sol-12-runs/index.html\">Previous report</a></p>"
        "<h2>Expandable per-run findings</h2>" + "".join(details) + "</main></html>"
    )
    (HERE / "index.html").write_text(page)
    return summary


def restore(result, viewer):
    from agenttrace.store import Store

    if viewer.exists():
        raise ValueError("Restore destination must not exist.")
    viewer.mkdir(parents=True)
    baseline = ROOT / "data/programbench-pr10/agenttrace.sqlite3"
    with sqlite3.connect(f"file:{baseline}?mode=ro", uri=True) as source:
        with sqlite3.connect(viewer / "agenttrace.sqlite3") as target:
            source.backup(target)
    store = Store(viewer)
    for row in result["runs"]:
        for record in [*row["offline_analyses"].values(), row["scout"], row["previous_communication"], row["communication"]]:
            store.save_run(record)
    print(f"Restored {len(result['runs'])} saved runs; no source capture or generation was used.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "restore"])
    parser.add_argument("--work", type=Path)
    parser.add_argument("--viewer", type=Path, required=True)
    parser.add_argument("--viewer-base", default="http://127.0.0.1:3013")
    args = parser.parse_args()
    if args.command == "restore":
        restore(read(HERE / "results.json"), args.viewer)
    else:
        if args.work is None:
            parser.error("--work is required for build")
        result = assemble(args.work, args.viewer, args.viewer_base)
        print(json.dumps(render(result), indent=2))
