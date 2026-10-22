"""Publish or restore saved fresh judgments without model/provider generation."""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import html
import json
import re
import runpy
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCOUT = ("duplicated_work", "weak_handoff", "unintegrated_information")
COMM = ("disclosure", "delivery", "reading", "action")
STAGES = ("search-A", "search-B", "A", "B", "judge")
PARENT_SESSION = "141c12e0-1ebe-4856-92f6-738fb99cce57"
DIRECT_METHOD = "direct single-session"
INDEPENDENT_METHOD = "independent A/B + judge"
DIRECT_SLUGS = {f"xsv-n{n}-round{r}" for n in (2, 3) for r in (1, 2, 3)}
LABELS = {
    "duplicated_work": "Scout: duplicated work",
    "weak_handoff": "Scout: weak handoff",
    "unintegrated_information": "Scout: unintegrated information",
    **{key: f"Incident: {key} failure" for key in COMM},
}
FLAGS = {"supported_failure": "yes", "no_failure_found": "no", "undecidable": "unknown"}
DEFINITIONS = {
    "duplicated_work": "Different agents repeat materially equivalent work without a useful verification, synthesis, handoff or corrective purpose.",
    "weak_handoff": "A concrete request or commitment is abandoned, its result is not delivered/integrated, or conflicting ownership causes observable coordination failure. Silence alone is insufficient.",
    "unintegrated_information": "A later dependent decision ignores or contradicts relevant shared information despite positive evidence of an opportunity to use it. Publication order alone is insufficient.",
    "disclosure": "An agent knows relevant information but fails to share it clearly, accurately and in time when sharing is required.",
    "delivery": "Clearly shared information does not reach the intended recipient before relevant actual work. Publication/native stdout alone does not establish model-visible receipt.",
    "reading": "The recipient receives a clear message but expresses an incorrect interpretation or forgets it. Receipt alone does not establish understanding.",
    "action": "The recipient receives and correctly understands a commitment, but subsequent execution violates it. An ordinary coding error alone does not qualify.",
}
REASONS = {
    "missing_source_evidence": "Required evidence was not captured in the frozen export.",
    "evidence_not_retrieved": "Required evidence is outside the retrieved review packet.",
    "ambiguous_cause": "The cause or responsible transition remains unresolved.",
    "unclear_obligation": "The relevant commitment or duty to share is unestablished.",
    "unclear_understanding": "Recipient interpretation or retention is unestablished.",
    "ambiguous_timing": "Publication, receipt or action ordering is unresolved.",
}
LEGEND = (
    "**yes** = this failure type was flagged; communication requires a final supported incident. "
    "**no** = no qualifying failure was flagged; communication negatives apply only to complete reviewed scopes, "
    "not the whole run or every possible failure. **unknown** = insufficient evidence to decide, neither yes nor no. "
    "Scout is binary and cannot report unknown. A/B proposals alone are not final flags. "
    "A rejected candidate is not a run-level No; another candidate can still be supported or unknown. "
    "Repair does not erase a failure; breakdown and downstream harm are separate."
)
CAVEATS = [
    "Fresh GPT-6.1 Sol Copilot-session judgments, not native Inspect/provider generation or human ground truth.",
    "Scout targets and the collaboration scan share one context per trace, including possible later-target lookahead; not 614 independent native calls.",
    "Mixed review protocol: six traces use independent A/B + judge; six xsv n2/n3 traces use a direct single-session Assessment. No full-cohort A/B agreement statistic is valid.",
    "66 previously launched agent contexts: 12 Scout + 24 search + 24 review + 6 judge; 57 succeeded and 9 failed. Failed stages remain failed, not replaced with fabricated A/B or judge replies.",
    "Six direct assessments were authored in parent session 141c12e0-1ebe-4856-92f6-738fb99cce57, sharing context; they are not six independent contexts. Original successful searches are reused. Surviving A proposals are prior attempts, ignored for direct decisions.",
    "Direct-review prompt files are reconstructed application input inventories for staged reads in the existing shared parent context, not separately submitted independent prompts. The complete parent conversation is not reconstructed.",
    "Direct review covers all non-goal communication posts, indexed command/receipt discovery, and selected inspected full source events, not the entire union or full trace. Omitted source details are evidence_not_retrieved, not missing_source_evidence. Direct judgments do not provide robustness comparable to independent A/B + judge.",
    "Execution counters describe saved-response validation, not additional inference or provider billing. Copilot internal turns, HTTP requests, billed calls and tokens are not measured.",
    "Independent same-model judgments can share errors. Validation verifies structure, citations and evidence scopes, not semantic accuracy.",
    "No is a scoped negative, not universal absence. Unknown is not No. Receiving text is not proof of understanding.",
    "Source-complete retrieval certificates cover specific actor/time windows, not whole-run completeness. Reviewer-selected source events alone do not certify complete windows or justify absence claims.",
    "Recorded inputs/tool outputs are not complete serialized model API requests; workspace checkpoints have batch-level timing and causal-attribution limits.",
    "v0.2-to-v0.3 changes mix evidence access, decision rules and sampling; this is not a controlled ablation or an accuracy-improvement measurement.",
    "Localhost viewer links require the matching restored database on the reader's machine, or rewriting links to a shared viewer.",
]


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def credential_check(text):
    pattern = r"(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
    if re.search(pattern, text):
        raise ValueError("Potential credential in publication input; inspect locally before publishing.")


def archive_write(value):
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    credential_check(encoded.decode())
    with (HERE / "prompt-replay.json.gz").open("wb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
            compressed.write(encoded)


def archive_read():
    with gzip.open(HERE / "prompt-replay.json.gz", "rt", encoding="utf-8") as stream:
        return json.load(stream)


def review_method(directory):
    return DIRECT_METHOD if (directory / "direct-review.reply.json").is_file() else INDEPENDENT_METHOD


def execution_inputs(work, manifest):
    """Accept only real assignments; direct work is one shared parent context."""
    agents = read(work / "agents.json")
    slugs = {row["slug"] for row in manifest["rows"]}
    if len(slugs) != 12 or set(agents) != slugs:
        raise ValueError("Need actual successful role assignments for exactly the 12 manifest traces.")
    methods = {slug: review_method(work / slug) for slug in slugs}
    if {slug for slug, method in methods.items() if method == DIRECT_METHOD} != DIRECT_SLUGS:
        raise ValueError("Mixed publication requires direct replies for the six xsv n2/n3 traces only.")
    for slug, roles in agents.items():
        required = {"scout", "search-A", "search-B"}
        allowed = required | {"A"}
        if methods[slug] == INDEPENDENT_METHOD:
            required = allowed = {"scout", *STAGES}
        if not required <= set(roles) <= allowed or any(not isinstance(v, str) or not v for v in roles.values()):
            raise ValueError(f"Missing or unsupported actual successful roles: {slug}")
    raw = read(work / "execution-attempts.json")
    attempts = raw["attempts"] if isinstance(raw, dict) else raw
    if not isinstance(attempts, list) or len(attempts) != 66:
        raise ValueError("execution-attempts.json must contain all 66 real assignments.")
    if any(set(("slug", "role", "agent_id", "status")) - set(item) for item in attempts):
        raise ValueError("Each attempt requires slug, role, agent_id and status (completed/succeeded or failed).")
    if Counter("succeeded" if item["status"] == "completed" else item["status"] for item in attempts) != Counter({"succeeded": 57, "failed": 9}):
        raise ValueError("Expected the actual 57 succeeded and 9 failed contexts.")
    if len({item["agent_id"] for item in attempts}) != 66 or any(
        not isinstance(item["agent_id"], str) or not item["agent_id"] or item["agent_id"] == PARENT_SESSION
        or item["slug"] not in slugs or item["role"] not in {"scout", *STAGES} for item in attempts
    ):
        raise ValueError("Assignments require 66 distinct real agent IDs and known trace/role pairs.")
    if Counter(item["role"] for item in attempts) != Counter(
        {"scout": 12, "search-A": 12, "search-B": 12, "A": 12, "B": 12, "judge": 6}
    ):
        raise ValueError("Actual launches must be 12 Scout, 24 search, 24 review and 6 judge.")
    expected_pairs = {
        (slug, role) for slug in slugs
        for role in (("scout", "search-A", "search-B", "A", "B") if methods[slug] == DIRECT_METHOD else ("scout", *STAGES))
    }
    if {(item["slug"], item["role"]) for item in attempts} != expected_pairs:
        raise ValueError("Need every actual launched trace/role pair exactly once; no judge was launched for direct traces.")
    successful = {(item["slug"], item["role"], item["agent_id"]) for item in attempts if item["status"] in ("succeeded", "completed")}
    declared = {(slug, role, identifier) for slug, roles in agents.items() for role, identifier in roles.items()}
    if successful != declared or len(declared) != 57:
        raise ValueError("agents.json must exactly match all 57 successful assignments, including prior A attempts.")
    accounting = {
        "launched_agent_contexts": 66, "succeeded_agent_contexts": 57, "failed_agent_contexts": 9,
        "scout": 12, "search": 24, "review": 24, "judge": 6,
        "direct_assessments": 6, "direct_reviewer_session": PARENT_SESSION,
        "direct_reviewer_contexts": 1, "direct_context_is_shared": True,
        "count_basis": "Prior launched agent jobs; six additional direct assessments share the existing parent context, not six new independent jobs.",
    }
    return agents, attempts, methods, accounting


def assemble(work, viewer, viewer_base):
    from agenttrace.api import SCOUT_PROMPT_VERSION, SCOUT_VERSION
    from agenttrace.communication.evidence import digest
    from agenttrace.models import AnalysisRun, Analyzer, Provenance
    from agenttrace.store import Store

    manifest = read(work / "manifest.json")
    for name, expected in manifest["source_code_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f"Frozen implementation changed: {name}")
    agents, attempts, methods, accounting = execution_inputs(work, manifest)
    harness = runpy.run_path(str(HERE / "replay.py"))
    previous = {row["slug"]: row for row in read(ROOT / "reports/2026-10-19-richer-evidence-12-runs/results.json")["runs"]}
    store = Store(viewer)
    completed = datetime.now(timezone.utc).isoformat()
    rows, archived = [], {}
    for source in manifest["rows"]:
        slug = source["slug"]
        directory = work / slug
        asyncio.run(harness["scout"](work, slug))
        is_direct = methods[slug] == DIRECT_METHOD
        asyncio.run(harness["direct" if is_direct else "communication"](work, slug))
        report = read(directory / "report.input.json")
        bundle = read(directory / "evidence.json")
        if digest({k: v for k, v in bundle.items() if k != "sha256"}) != source["evidence_sha256"]:
            raise ValueError(f"Source evidence changed: {slug}")
        records = {}
        for key, name, version, prompt_version in (
            ("scout", "scout_collaboration_v1", SCOUT_VERSION, SCOUT_PROMPT_VERSION),
            ("communication", "communication_failures_v1", manifest["communication_version"], manifest["communication_prompt_version"]),
        ):
            output = read(directory / f"{key}.result.json")
            roles = ("scout",) if key == "scout" else (("search-A", "search-B") if is_direct else STAGES)
            output["session_replay"] = {
                "surface": manifest["execution"], "requested_model": "gpt-6.1-sol",
                "agents": {role: agents[slug][role] for role in roles},
                "direct_provider_api_calls": 0, "caveat": CAVEATS[1 if key == "scout" else 2],
            }
            if key == "communication":
                output["method"] = methods[slug]
                output["session_replay"]["execution_attempts"] = [item for item in attempts if item["slug"] == slug and item["role"] != "scout"]
                if is_direct:
                    output["session_replay"]["direct_reviewer"] = {"session_id": PARENT_SESSION, "shared_context": True}
                    output["session_replay"]["prior_review_attempts_ignored"] = {
                        role: identifier for role, identifier in agents[slug].items() if role in ("A", "B", "judge")
                    }
            record = AnalysisRun(
                id=f"run_v03fresh12_{slug}_{key}", trace_id=source["trace_id"],
                analyzer=Analyzer(name=name, version=version, kind="pipeline"), status="completed",
                provenance=Provenance(
                    completed_at=completed, model=manifest["model"], prompt_version=prompt_version,
                    taxonomy_version="communication-transitions/1" if key == "communication" else None,
                    evidence_sha256=source["evidence_sha256"] if key == "communication" else None,
                    configuration_sha256=digest({
                        "analyzer": name, "version": version, "prompt": prompt_version,
                        "model": manifest["model"], "execution": manifest["execution"],
                        "source": source["evidence_sha256"], "source_code": manifest["source_code_sha256"],
                        "method": methods[slug] if key == "communication" else "grouped Scout session",
                    }),
                ), output=output,
            ).record()
            records[key] = record
            store.save_run(record)
        required_files = [
            "annotations.reply.json", "collaboration.reply.json", "collaboration.prompt.txt",
            "message-prompts.json", "annotation.schema.json", "collaboration.schema.json",
            "report.input.json", "evidence.json", "discovery-evidence.json",
            *[f"{tag}.{suffix}" for tag in (("search-A", "search-B", "direct-review") if is_direct else STAGES)
              for suffix in ("prompt.txt", "reply.json", "schema.json")],
            *(["direct-review-evidence.json"] if is_direct else ["A-review-evidence.json", "B-review-evidence.json", "union-evidence.json"]),
        ]
        for name in required_files:
            if not (directory / name).is_file():
                raise ValueError(f"Required replay artifact missing: {slug}/{name}")
        filenames = sorted(set(required_files) | {
            path.name for path in directory.iterdir() if path.is_file() and (
                path.name.endswith((".prompt.txt", ".reply.json", ".schema.json", "-evidence.json"))
            )
        })
        source = {
            **source,
            "source_event_text_chars": sum(len(event["text"]) for event in bundle["events"]),
            "discovery_event_text_chars": sum(
                len(event["text"]) for event in read(directory / "discovery-evidence.json")["events"]
            ),
            "final_review_event_text_chars": sum(
                len(event["text"]) for event in records["communication"]["output"]["evidence"]
            ),
        }
        rows.append({
            "slug": slug, "trace_id": source["trace_id"], "communication_review_method": methods[slug],
            "review_protocol": (
                records["communication"]["output"]["protocol"] if is_direct else
                {"kind": "independent-ab-judge", "independent_ab": True, "judge": True,
                 "input_record_kind": "exact submitted application stage prompts"}
            ),
            "agenttrace_url": viewer_base + "/?" + urlencode({"trace": source["trace_id"], "analysis": records["communication"]["id"]}),
            "metrics": report["metrics"], "structural_flags": report["failureModes"],
            **records, "input": source,
            "artifact_sha256": {name: sha(directory / name) for name in filenames},
        })
        archived[slug] = {
            "review_protocol": rows[-1]["review_protocol"],
            "source_evidence": bundle, "scout_report_input": report,
            "message_prompts": read(directory / "message-prompts.json"),
            "annotation_schema": read(directory / "annotation.schema.json"),
            "collaboration_schema": read(directory / "collaboration.schema.json"),
            "files": {name: (directory / name).read_text(encoding="utf-8") for name in filenames},
            "review_packets": {
                tag: read(directory / f"{tag}-review-evidence.json") for tag in ("A", "B")
                if not is_direct and (directory / f"{tag}-review-evidence.json").is_file()
            },
            "prior_attempt_review_packets": {
                tag: read(directory / f"{tag}-review-evidence.json") for tag in ("A", "B")
                if is_direct and (directory / f"{tag}-review-evidence.json").is_file()
            },
            "direct_review_packet": read(directory / "direct-review-evidence.json") if is_direct else None,
            "artifact_provenance": {
                name: ("prior attempt, not used for direct decisions" if is_direct and name.startswith(("A.", "B.", "judge.", "A-review-", "B-review-", "union-"))
                       else "reconstructed staged-read input inventory in shared parent context; not a separately submitted model prompt"
                       if is_direct and name == "direct-review.prompt.txt"
                       else "reused original search input/output" if is_direct and name.startswith(("search-", "discovery-"))
                       else "publication review/scout input/output")
                for name in filenames
            },
        }
    result = {
        "schema": "agenttrace/fresh-v03-session-report.v1", "completed_at": completed,
        **{k: manifest[k] for k in (
            "model", "execution", "direct_provider_api_calls", "source_commit",
            "source_code_sha256", "rubric_sha256", "communication_version", "communication_prompt_version",
        )},
        "fresh_scout": True, "session_jobs": accounting,
        "review_protocol": {"kind": "mixed", "independent_ab_judge_traces": 6, "direct_single_session_traces": 6,
                            "full_cohort_ab_agreement": "not applicable: mixed protocols"},
        "replay_harness_sha256": sha(HERE / "replay.py"),
        "caveats": CAVEATS, "runs": rows,
        "previous_v02_counts": {
            key: dict(Counter(c["status"] for row in previous.values() for c in row["communication"]["output"]["classes"] if c["failure_class"] == key))
            for key in COMM
        },
    }
    credential_check(json.dumps(result))
    archive_write({
        "schema": "agenttrace/session-prompt-artifacts.v1", "manifest": manifest,
        "session_instructions": (work / "AGENT.txt").read_text(), "agents": agents, "runs": archived,
        "execution_attempts": attempts, "execution_accounting": accounting,
        "execution_input_files": {name: (work / name).read_text(encoding="utf-8") for name in ("agents.json", "execution-attempts.json")},
        "execution_input_sha256": {name: sha(work / name) for name in ("agents.json", "execution-attempts.json")},
        "caveat": "Independent stages preserve exact submitted application prompts/schemas/replies. Direct-review prompt files are reconstructed staged-read inventories in the shared parent context, not separately submitted model prompts. Neither captures complete Copilot system wrappers, conversations or internal request counts.",
    })
    result["prompt_replay_sha256"] = sha(HERE / "prompt-replay.json.gz")
    write(HERE / "results.json", result)
    return result


def restore(result, destination):
    from agenttrace.communication.evidence import digest
    from agenttrace.store import Store

    if destination.exists():
        raise ValueError("Restore destination must not exist.")
    if sha(HERE / "prompt-replay.json.gz") != result["prompt_replay_sha256"]:
        raise ValueError("Replay archive hash mismatch.")
    archive = archive_read()
    destination.mkdir(parents=True)
    source_db = ROOT / "data/programbench-pr10/agenttrace.sqlite3"
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as source:
        with sqlite3.connect(destination / "agenttrace.sqlite3") as target:
            source.backup(target)
    store = Store(destination)
    for row in result["runs"]:
        evidence = archive["runs"][row["slug"]]["source_evidence"]
        if digest({k: v for k, v in evidence.items() if k != "sha256"}) != row["input"]["evidence_sha256"]:
            raise ValueError(f"Evidence restore hash mismatch: {row['slug']}")
        store.save_evidence(row["trace_id"], evidence)
        for key in ("scout", "communication"):
            store.save_run(row[key])


def summary(result):
    rows = result["runs"]
    if len(rows) != 12 or sum(row["input"]["messages"] for row in rows) != 602:
        raise ValueError("Expected all 12 traces and 602 fresh Scout annotations.")
    counts = {key: Counter() for key in (*SCOUT, *COMM)}
    incidents, unknown_reasons, flags = Counter(), Counter(), []
    unresolved = impact_observed = 0
    for row in rows:
        scout = row["scout"]["output"]
        communication = row["communication"]["output"]
        if len(scout["annotations"]) != row["input"]["messages"]:
            raise ValueError(f"Missing fresh annotations: {row['slug']}")
        selected = {f["category"]: "yes" if f["found"] else "no" for f in scout["findings"]}
        if set(selected) != set(SCOUT) or {c["failure_class"] for c in communication["classes"]} != set(COMM):
            raise ValueError("Incomplete metric set.")
        for item in communication["classes"]:
            selected[item["failure_class"]] = FLAGS[item["status"]]
            unknown_reasons.update(item["unknown_reasons"])
        for key, value in selected.items():
            counts[key][value] += 1
        for incident in communication["incidents"]:
            if incident["status"] == "supported":
                incidents[incident["failure_class"]] += 1
                impact_observed += incident["impact_status"] == "observed"
            else:
                unresolved += 1
        flags.append({
            "slug": row["slug"], "agenttrace_url": row["agenttrace_url"],
            "communication_review_method": row["communication_review_method"], "flags": selected,
        })
    return {
        "model": result["model"], "communication_version": result["communication_version"],
        "runs": 12, "fresh_scout_annotations": 602, "fresh_scout_findings": 36,
        "communication_class_decisions": 48, "session_jobs": result["session_jobs"],
        "review_protocol": result["review_protocol"],
        "flags_by_metric": {key: {flag: counts[key][flag] for flag in ("yes", "no", "unknown")} for key in counts},
        "supported_incidents": {key: incidents[key] for key in COMM},
        "unresolved_incident_candidates": unresolved, "supported_incidents_with_observed_impact": impact_observed,
        "unknown_class_reasons": dict(unknown_reasons), "rows": flags,
    }


def render(result):
    totals = summary(result)
    write(HERE / "summary.json", totals)
    headers = ["Run / AgentTrace visualization", "Communication review method", *[LABELS[key] for key in (*SCOUT, *COMM)]]
    markdown_rows, html_rows = [], []
    for row in totals["rows"]:
        cells = [row["flags"][key] for key in (*SCOUT, *COMM)]
        markdown_rows.append(f"| [{row['slug']}]({row['agenttrace_url']}) | {row['communication_review_method']} | " + " | ".join(cells) + " |")
        html_rows.append(
            f'<tr><th><a href="{html.escape(row["agenttrace_url"], quote=True)}">{row["slug"]}</a></th>'
            + f'<td>{html.escape(row["communication_review_method"])}</td>'
            + "".join(f'<td class="{value}">{value}</td>' for value in cells) + "</tr>"
        )
    table_md = "| " + " | ".join(headers) + " |\n|" + " --- |" * len(headers) + "\n" + "\n".join(markdown_rows)
    count_md = (
        "| Failure metric | Runs: yes | Runs: no | Runs: unknown | Supported incidents |\n"
        "| --- | --- | --- | --- | --- |\n"
        + "\n".join(
            f"| {LABELS[key]} | {totals['flags_by_metric'][key]['yes']} | {totals['flags_by_metric'][key]['no']} | "
            f"{totals['flags_by_metric'][key]['unknown']} | {totals['supported_incidents'][key] if key in COMM else 'not an incident metric'} |"
            for key in (*SCOUT, *COMM)
        )
    )
    definitions_md = "\n".join(f"| {LABELS[key]} | {DEFINITIONS[key]} |" for key in (*SCOUT, *COMM))
    unknown_total = sum(totals["flags_by_metric"][key]["unknown"] for key in COMM)
    supported_total = sum(totals["supported_incidents"].values())
    lead = (
        f"**Fresh Scout and communication v0.3 / prompt 3 for all 12 traces.** "
        f"602 new Scout annotations, 36 new Scout findings, and 48 final communication decisions. "
        f"Communication retains **{supported_total} supported incidents**, "
        f"**{totals['unresolved_incident_candidates']} unresolved candidates**, and **{unknown_total}/48 unknown class decisions**. "
        "These are model judgments, not ground truth."
    )
    readme = f"""# Fresh Scout + communication v0.3: 12 runs

{lead}

October 21, 2026. GPT-6.1 Sol Copilot-session replay; no environment OpenAI/Azure keys or direct provider API calls.
This is a separate report; the [October 19 v0.2 results](../2026-10-19-richer-evidence-12-runs/README.md) are preserved.

[HTML report](index.html) · [Complete judgments](results.json) · [Compact summary](summary.json) ·
[Stage prompts, reconstructed direct input inventories, replies, schemas and supplied evidence (gzip JSON)](prompt-replay.json.gz) ·
[Data-flow diagram and prompt definitions](../../docs/communication-analysis-flow.html)

## All seven failure flags

{table_md}

**Legend:** {LEGEND}

## Counts, not scores

{count_md}

Run columns each sum to 12. Incidents count individual first-transition breakdowns; a run can have multiple.
Unknown class reasons (one decision may have several): `{json.dumps(totals['unknown_class_reasons'], sort_keys=True)}`.
Of {supported_total} supported incidents, {totals['supported_incidents_with_observed_impact']} have separately evidenced downstream impact.
Missing proof of harm does not invalidate an observed breakdown; unestablished impact has null severity.

## Metric definitions

| Metric | What yes means |
| --- | --- |
{definitions_md}

Definitions: [Scout rubric (analyze_collaboration)](../../packages/agenttrace-api/agenttrace/scout/scanners.py);
[communication RUBRIC / Incident / ClassAssessment](../../packages/agenttrace-api/agenttrace/communication/analysis.py);
[retrieval/completeness rules](../../packages/agenttrace-api/agenttrace/communication/evidence.py).
Communication assigns only the first evidenced failed transition: disclosure → delivery → reading → action.
See the HTML report for final class decisions, explicit unknown reasons, evidence scopes and incidents.
Only the six independent-review traces have A/B proposals and candidate adjudication.

## Execution and limitations

**Mixed review protocol.** Six traces retain their completed independent A/B + judge outputs unchanged.
The six xsv n2/n3 traces instead use **direct single-session** Assessments authored by the parent in shared
session `{PARENT_SESSION}`; these are not independent A/B reviews, judge results, or six independent jobs.
Original successful search-A/B replies are reused. Surviving A proposals are archived as prior attempts and
ignored for direct decisions. There are no synthetic A/B annotations or candidate adjudication decisions.
No full-cohort A/B agreement statistic is reported.
**The direct-review prompt files are reconstructed application input inventories of staged reads in the
existing shared parent context, not separately submitted independent model prompts.** They do not reconstruct
the entire parent conversation. Direct judgments are not comparable in robustness to independent A/B + judge.

**66 previously launched agent contexts: 12 Scout + 24 search + 24 review + 6 judge;
57 succeeded, 9 failed.** The failed review stages remain failed. Six additional direct assessments share
the existing parent session. Exact assignments and failure statuses are archived.
The independent traces use the native five-stage pipeline with saved replies; direct traces bypass it
and validate only their actual Assessment and the two reused searches.
Saved-response validation counters are **not inference calls or billed API-call counts**.
Scout's native formula would be 602 annotation generations + 12 collaboration generations without retries;
our per-trace grouped sessions are **not 614 independent native calls**.
Copilot-internal turns, requests, tokens and billing are unmeasured.

Source: xisen-w/multi-agent-training#3, pinned to `{result['source_commit']}`.
The gzip archive includes exact submitted independent-stage prompts, reconstructed direct-review input
inventories, schemas/replies, fresh Scout input, full frozen source evidence,
and the exact packet supplied to each actual reviewer. Direct review need not use the A/B union:
its exact supplied packet determines the published evidence and coverage.
Direct input selection consists of all non-goal communication posts, indexed command/receipt discovery,
and selected fully inspected source events. This does not mean the whole union or full trace was reviewed.
Omitted source details are **evidence_not_retrieved**, not missing_source_evidence.
Source-complete certificates cover particular actor/time windows; reviewer-selected source events without
certificates cannot support scoped absence or negative claims. Copilot system wrappers/internal conversations are not captured.
`results.json` records session IDs, source/code hashes and prompt/reply hashes.

{chr(10).join('- ' + item for item in CAVEATS)}

## Share or restore without inference

Send `index.html` for a standalone readable report; send this folder for judgments and replay artifacts.
**Visualization links use 127.0.0.1:3014:** teammates need their own restored local viewer, or a shared viewer.
Repository/documentation links require the surrounding checkout.

```bash
env -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY \\
  PYTHONPATH=packages/commsfail:packages/agenttrace-api \\
  .venv/bin/python reports/2026-10-21-v03-12-runs/build_report.py \\
  restore --viewer .agenttrace/restored-v03
env -u OPENAI_API_KEY -u AZURE_OPENAI_API_KEY \\
  PYTHONPATH=packages/commsfail:packages/agenttrace-api \\
  .venv/bin/python reports/2026-10-21-v03-12-runs/viewer.py \\
  --viewer .agenttrace/restored-v03 --port 3014
```

Restore copies the checked-in baseline SQLite into a new directory, verifies the archived evidence, and saves only
these new analysis records. It never initializes the original database or invokes a model.
Regenerate the readable reports with `python3 reports/2026-10-21-v03-12-runs/build_report.py render`.
"""
    (HERE / "README.md").write_text(readme, encoding="utf-8")
    details = []
    for row in result["runs"]:
        output = row["communication"]["output"]
        is_direct = row["communication_review_method"] == DIRECT_METHOD
        decisions = []
        for key in COMM:
            values = [
                next(item for item in assessment["classes"] if item["failure_class"] == key)
                for assessment in ((output,) if is_direct else (output["annotations"]["A"], output["annotations"]["B"], output))
            ]
            final = values[-1]
            scopes = "; ".join(
                f'{", ".join(scope["actors"])}: {scope["start_event"]} to {scope["end_event"]}'
                for scope in final["evidence_scope"]
            ) or "No scoped-negative certificate claimed."
            decisions.append(
                f"<tr><th>{LABELS[key]}</th>"
                + "".join(f'<td class="{FLAGS[v["status"]]}">{FLAGS[v["status"]]}</td>' for v in values)
                + f'<td>{html.escape(final["explanation"])}<p><b>Unknown reasons:</b> '
                + html.escape("; ".join(final["unknown_reasons"]) or "none")
                + f'</p><p><b>Reviewed scope:</b> {html.escape(scopes)}</p></td></tr>'
            )
        incident_html = []
        for incident in output["incidents"]:
            evidence = "".join(
                f'<blockquote>{html.escape(c["quote"])} <small>({html.escape(c["event_id"])})</small></blockquote>'
                for transition in incident["transitions"].values() for c in transition["evidence"]
            )
            incident_html.append(
                f'<li><b>{html.escape(incident["id"])}: {html.escape(incident["work_item"])}</b>'
                f'<p>{html.escape(str(incident["failure_class"]))}; {incident["status"]}; '
                f'impact: {incident["impact_status"]}; severity: {incident["severity"]}; recovery: {incident["recovery"]["status"]}.</p>'
                f'<p>{html.escape(incident["consequence"])}</p>{evidence}</li>'
            )
        scout_html = "".join(
            f'<p><b>{LABELS[f["category"]]}: {"yes" if f["found"] else "no"}</b> {html.escape(f["explanation"])}</p>'
            for f in row["scout"]["output"]["findings"]
        )
        adjudications = "".join(
            f'<li><code>{html.escape(d["candidate_id"])}</code>: {d["decision"]}'
            f' → {html.escape(d["final_incident_id"] or "not retained")}. {html.escape(d["reason"])}</li>'
            for d in output.get("decisions", [])
        )
        decision_headers = (
            "<th>Direct assessment</th>" if is_direct else "<th>Review A</th><th>Review B</th><th>Final judge</th>"
        )
        adjudication_section = (
            "<h3>Direct-review provenance</h3><p>No independent A/B or judge. No candidate adjudication was performed. "
            f"Reviewer: parent session <code>{PARENT_SESSION}</code>, shared context. Original searches reused; "
            "any surviving earlier A proposals were ignored for direct decisions.</p>"
            "<p><b>Reconstructed application input inventory:</b> direct-review.prompt.txt describes staged reads "
            "in the existing shared parent context, not a separately submitted independent model prompt. "
            "Selection includes all non-goal communication posts, indexed command/receipt discovery, and "
            "selected fully inspected source events, not the entire union or full trace. Omitted source "
            "details are evidence_not_retrieved. Robustness is not comparable to independent A/B + judge.</p>"
            if is_direct else "<h3>Candidate adjudication</h3><ul>"
            + (adjudications or "<li>No candidates proposed.</li>") + "</ul>"
        )
        coverage = output["coverage"]
        complete = sum(bool(certificate["source_complete"]) for certificate in coverage.get("retrieval_windows", []))
        scope_note = (
            f'Review packet: {len(output["evidence"])} supplied events; '
            f'{len(coverage.get("omitted_events", []))} omitted source events; '
            f'{complete} source-complete actor/time window certificates. '
            "Only certified reviewed scopes support No or absence; selected events do not establish whole-run completeness."
        )
        details.append(
            f'<details id="{row["slug"]}" data-review-method="{html.escape(row["communication_review_method"], quote=True)}">'
            f'<summary>{row["slug"]}: {row["communication_review_method"]}</summary>'
            f'{scout_html}<p>{html.escape(output["explanation"])}</p>'
            f'<p>{html.escape(scope_note)}</p>'
            '<div class="scroll"><table><thead><tr><th>Failure type</th>' + decision_headers
            + '<th>Final explanation, uncertainty and scope</th></tr></thead><tbody>'
            + "".join(decisions) + "</tbody></table></div><h3>Final incidents and unresolved candidates</h3><ul>"
            + ("".join(incident_html) or "<li>No retained incidents.</li>")
            + "</ul>" + adjudication_section + "</details>"
        )
    definition_html = "".join(
        f'<tr id="metric-{key}"><th>{LABELS[key]}</th><td>{DEFINITIONS[key]}</td></tr>' for key in (*SCOUT, *COMM)
    )
    simple_legend = LEGEND.replace("**", "")
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fresh Scout + communication v0.3: 12 runs</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1280px;margin:35px auto;padding:0 22px;color:#182b3d;background:#fafbfc}}
a{{color:#125ca5}}table{{border-collapse:collapse;width:100%;background:white;margin:15px 0}}
th,td{{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #dce3eb}}thead{{background:#edf2f8}}
.scroll{{overflow:auto}}.yes{{color:#a72d22;font-weight:650}}.no{{color:#275e43}}.unknown{{color:#846014;font-weight:650}}
.note{{background:#edf3fa;border-left:4px solid #4b78aa;padding:14px 18px}}small{{color:#596878}}
details{{border-top:1px solid #dce3eb;padding:14px 0}}summary{{cursor:pointer;font-weight:650}}
blockquote{{border-left:3px solid #cbd7e5;padding-left:12px;white-space:pre-wrap;overflow-wrap:anywhere}}
code{{overflow-wrap:anywhere}}h1{{line-height:1.2}}h2{{margin-top:30px}}
</style><main><h1>Fresh Scout + communication v0.3</h1>
<p>October 21, 2026 · 12 traces · GPT-6.1 Sol session replay · no direct provider/key calls</p>
<p>{html.escape(lead.replace("**", ""))}</p>
<p><a href="README.md">GitHub-readable report</a> · <a href="results.json">Complete judgments</a> ·
<a href="summary.json">Compact summary</a> · <a href="prompt-replay.json.gz">Stage prompts, direct input inventories and evidence archive</a> ·
<a href="../../docs/communication-analysis-flow.html">Flow, prompts and call counts</a></p>
<h2>All seven flags</h2><p>All Scout and communication judgments are new. One row per run; cells are flags, not counts.</p>
<div class="scroll"><table id="combined-results"><thead><tr><th>{headers[0]}</th><th>{headers[1]}</th>
{''.join(f'<th><a href="#metric-{key}">{LABELS[key]}</a></th>' for key in (*SCOUT, *COMM))}
</tr></thead><tbody>{''.join(html_rows)}</tbody></table></div>
<p id="legend"><b>Legend:</b> {html.escape(simple_legend)}</p>
<h2>Counts and uncertainty</h2><p>Each metric has 12 run decisions. Supported incident counts describe individual
breakdowns, not runs; unresolved candidates are not flagged failures.</p>
<table id="totals"><thead><tr><th>Failure metric</th><th>Runs: yes</th><th>Runs: no</th><th>Runs: unknown</th><th>Supported incidents</th></tr></thead><tbody>
{''.join(f'<tr><th>{LABELS[key]}</th><td>{totals["flags_by_metric"][key]["yes"]}</td><td>{totals["flags_by_metric"][key]["no"]}</td><td>{totals["flags_by_metric"][key]["unknown"]}</td><td>{totals["supported_incidents"][key] if key in COMM else "not an incident metric"}</td></tr>' for key in (*SCOUT, *COMM))}
</tbody></table>
<p>{supported_total} supported incidents; {totals["supported_incidents_with_observed_impact"]} have separately evidenced downstream
impact. Unproven harm does not erase a breakdown; its severity remains null.</p>
<table><thead><tr><th>Unknown reason</th><th>Meaning</th><th>Unknown class decisions with this reason</th></tr></thead><tbody>
{''.join(f'<tr><th><code>{key}</code></th><td>{value}</td><td>{totals["unknown_class_reasons"].get(key, 0)}</td></tr>' for key, value in REASONS.items())}
</tbody></table>
<h2>Metric definitions</h2><table><thead><tr><th>Metric</th><th>What yes means</th></tr></thead><tbody>{definition_html}</tbody></table>
<p>Definitions: <a href="../../packages/agenttrace-api/agenttrace/scout/scanners.py">Scout analyze_collaboration</a>;
<a href="../../packages/agenttrace-api/agenttrace/communication/analysis.py">communication RUBRIC and response schemas</a>;
<a href="../../packages/agenttrace-api/agenttrace/communication/evidence.py">retrieval/completeness rules</a>.
Communication counts only the first evidenced failed transition: disclosure → delivery → reading → action.</p>
<h2>Per-run explanations and adjudication</h2>{''.join(details)}
<h2>Execution and sharing</h2>
<p><b>Mixed review protocol:</b> six independent A/B + judge traces and six direct single-session traces.
<b>66 prior launched agent contexts:</b> 12 Scout + 24 search + 24 review + 6 judge; 57 succeeded, 9 failed.
Six direct assessments share parent session <code>{PARENT_SESSION}</code>, not six independent contexts.
Direct reviews reuse original searches and ignore surviving A proposals. Failed stages remain failed.
Direct saved-response validation is not inference and does not execute a synthetic five-stage pipeline.
There is no full-cohort A/B agreement statistic.
Direct-review prompt files are reconstructed staged-read input inventories, not separately submitted prompts;
these judgments do not provide comparable independent robustness. The actual independent-stage application
prompts and exact supplied direct packets are preserved. Native no-retry Scout would use 614 independent generations;
this grouped replay does not. Copilot-internal requests/turns and billed calls are unmeasured.</p>
<ul>{''.join('<li>' + html.escape(item) + '</li>' for item in CAVEATS)}</ul>
<p class="note"><b>Share this HTML for a standalone readable report.</b> Send the report folder for all judgments and
prompt/evidence artifacts. Run links use <b>127.0.0.1:3014</b>; they require a local restored viewer or a shared deployment.
<a href="README.md">Model-free restoration instructions</a>. The separate
<a href="../2026-10-19-richer-evidence-12-runs/index.html">v0.2 report</a> remains historical, not overwritten.</p>
</main></html>
"""
    (HERE / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["assemble", "render", "restore"])
    parser.add_argument("--work", type=Path)
    parser.add_argument("--viewer", type=Path)
    parser.add_argument("--viewer-base", default="http://127.0.0.1:3014")
    args = parser.parse_args()
    if args.command == "assemble":
        render(assemble(args.work, args.viewer, args.viewer_base))
    elif args.command == "restore":
        restore(read(HERE / "results.json"), args.viewer)
    else:
        render(read(HERE / "results.json"))


if __name__ == "__main__":
    main()
