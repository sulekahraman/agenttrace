"""Build the progress report from frozen evidence; Python standard library only."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sqlite3


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATASET = ROOT / "data" / "teammate-traces"
DATA_COMMIT = "fd0be2ee134c2a355de55f3442c167652840bedd"
GITHUB = f"https://github.com/sulekahraman/agenttrace/blob/{DATA_COMMIT}/"
CATEGORIES = ("duplicated_work", "weak_handoff", "unintegrated_information")
LABELS = {
    "aziz-bundle-n4-r2": ("Bundle / 4 agents / r2", "Coding", (2, 3, 4, 5, 6, 7)),
    "aziz-bundle-n4-r1": ("Bundle / 4 agents / r1", "Coding", (12, 15, 16, 17)),
    "aziz-bundle-n3-r2": ("Bundle / 3 agents / r2", "Coding", (6, 9, 10)),
    "aziz-merger-n3": ("Merger / 3 agents", "Coding", (2, 3, 4, 5, 6, 7)),
    "xiangqian-noop007i2-solo": ("Arithmetic / solo", "Solo", (2,)),
    "xiangqian-noop007i2-pev": ("Arithmetic / P-E-V", "P-E-V", (2, 4, 5, 6)),
    "xiangqian-noop-stalled": ("Task-only room", "Task only", (1,)),
    "xiangqian-gpqa027-solo": ("GPQA / solo", "Solo", (2,)),
    "xiangqian-gpqa027-pev": ("GPQA / P-E-V", "P-E-V", (2, 6, 7, 8, 11, 12, 13)),
}
OBSERVATIONS = (
    "Competing splits; agents 3 and 4 both report finishing tasks 5-7.",
    "Task-3 overwrite warning, restoration, then another overwrite claim.",
    "An overwrite and restoration of recover.json are reported.",
    "Multiple agents report producing the same output files.",
    "Reports answer 10 and its own PASS; no independent grade.",
    "Selects whole-pack interpretation and answer 11 after asking the user.",
    "Only the task is visible; no observable agent activity.",
    "Reports answer B and its own PASS; no independent grade.",
    "Reported answer D to B to D; conflicting file-state reports.",
)
OWNERSHIP_QUOTES = {
    15: ("Warning", "DON'T touch task 3 plans"),
    16: ("Restoration claim", "Please don't overwrite plan_b*.jsonl."),
    17: ("Later overwrite claim", "I overwrote task-3 plans"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def link(url, text, **attributes):
    attrs = "".join(f' {key}="{escape(str(value), quote=True)}"' for key, value in attributes.items())
    return f'<a href="{escape(url, quote=True)}"{attrs}>{escape(str(text))}</a>'


def source_link(relative, text):
    return link(GITHUB + "data/teammate-traces/" + relative, text)


def message_link(trace, number, text=None):
    lines = (DATASET / trace["transcript_file"]).read_text(encoding="utf-8").splitlines()
    headers = [
        (int(match[1]), position)
        for position, line in enumerate(lines, start=1)
        if (match := re.match(r"^#(\d+) ", line))
    ]
    starts = dict(headers)
    require(number in starts, f"Missing transcript message: {trace['slug']} #{number}")
    start = starts[number]
    end = min((position - 1 for _, position in headers if position > start), default=len(lines))
    return source_link(
        trace["transcript_file"] + f"#L{start}-L{end}",
        text or f"{trace['ref']} #{number}",
    )


def refs(trace, numbers):
    return ", ".join(message_link(trace, number) for number in numbers)


def collect():
    manifest = load_json(DATASET / "manifest.json")
    require([trace["slug"] for trace in manifest["traces"]] == list(LABELS),
            "Changed cohort order; revisit the trace-specific observations")
    index = load_json(DATASET / manifest["analysis_index"])
    indexed = {entry["trace_id"]: entry for entry in index["traces"]}
    counts = Counter()
    analyzers = Counter()
    versions = Counter()
    primary_types = Counter()
    positives = Counter({category: 0 for category in CATEGORIES})
    dates = []
    selected_ids = set()
    traces = []

    for position, source in enumerate(manifest["traces"], start=1):
        report = load_json(DATASET / source["report_file"])
        agents = load_json(DATASET / source["agent_metrics_file"])
        entry = indexed[source["trace_id"]]
        require(report["traceId"] == entry["trace_id"], "Trace identity mismatch")
        messages = {message["index"]: message for message in report["messages"]}
        require(set(messages) == set(range(1, len(messages) + 1)), "Non-contiguous messages")
        records = []
        for selected in entry["analyses"]:
            if selected["status"] == "unavailable":
                require(selected["analyzer"] == "facts_v1", "Unexpected unavailable analyzer")
                counts["unavailable_facts"] += 1
                continue
            record = load_json(DATASET / "batch" / selected["file"])
            require(record == report["analyses"][selected["analyzer"]], "Selected result mismatch")
            require(record["status"] == "completed", "Selected run is not completed")
            require(record["trace_id"] == source["trace_id"], "Run trace mismatch")
            require(record["id"] == selected["run_id"], "Run identity mismatch")
            require(record["id"] not in selected_ids, "Duplicate selected run")
            selected_ids.add(record["id"])
            records.append({
                "analyzer": record["analyzer"]["name"],
                "run_id": record["id"],
                "file": "batch/" + selected["file"],
            })
            analyzers[record["analyzer"]["name"]] += 1
            dates.append(record["provenance"]["completed_at"])
        require(set(source["selected_run_ids"]) == {record["run_id"] for record in records},
                "Manifest selected IDs mismatch")

        scout = report["analyses"]["scout_collaboration_v1"]
        output = scout["output"]
        findings = output["findings"]
        coverage = output["coverage"]
        require(len(findings) == 3 and {finding["category"] for finding in findings} == set(CATEGORIES),
                "Expected exactly three collaboration judgments")
        require({item["message_number"] for item in output["annotations"]} == set(messages),
                "Annotation coverage mismatch")
        require(coverage["annotated_messages"] == len(messages), "Coverage count mismatch")
        for finding in findings:
            require(set(finding["message_numbers"]) <= set(messages), "Invalid finding evidence")
            require(not finding["found"] or finding["message_numbers"], "Uncited positive judgment")
            positives[finding["category"]] += int(finding["found"])
        for annotation in output["annotations"]:
            primary_types[annotation["primary_type"]] += 1
        provenance = scout["provenance"]
        versions[(provenance["model"], scout["analyzer"]["version"], provenance["prompt_version"])] += 1
        label, condition, evidence = LABELS[source["slug"]]
        agent_count = agents["visible_agent_posts"]
        operator_count = agents["excluded_operator_posts"]
        require(len(messages) == agent_count + operator_count, "Post-role counts mismatch")
        counts.update({
            "traces": 1,
            "visible_posts": len(messages),
            "agent_posts": agent_count,
            "task_operator_posts": operator_count,
            "message_annotations": len(output["annotations"]),
            "collaboration_judgments": len(findings),
            "candidate_messages": coverage["candidate_messages"],
            "candidate_count_truncated_traces": int(coverage["truncated"]),
            "messages_over_8000_characters": sum(len(item["text"]) > 8000 for item in messages.values()),
            "messages_over_2000_characters": sum(len(item["text"]) > 2000 for item in messages.values()),
            "visible_multi_agent_traces": int(agents["roster_agent_count"] > 1 and agent_count > 0),
            "solo_traces": int(condition == "Solo"),
            "task_only_traces": int(agent_count == 0),
        })
        traces.append({
            **source,
            "ref": f"E{position}",
            "label": label,
            "condition": condition,
            "evidence_messages": list(evidence),
            "observation": OBSERVATIONS[position - 1],
            "roster_agents": agents["roster_agent_count"],
            "agent_posts": agent_count,
            "operator_posts": operator_count,
            "all_post_p95_words": report["metrics"]["p95WordsPerMessage"],
            "agent_only_p95_words": (agents["metrics"] or {}).get("p95WordsPerMessage"),
            "source_dates": sorted({message["timestamp"][:10] for message in messages.values()}),
            "scout_run_id": scout["id"],
            "scout_version": scout["analyzer"]["version"],
            "prompt_version": provenance["prompt_version"],
            "model": provenance["model"],
            "findings": findings,
            "coverage": coverage,
            "selected_runs": records,
            "_messages": messages,
        })

    counts["selected_completed_analyses"] = sum(analyzers.values())
    counts["completed_scout"] = analyzers["scout_collaboration_v1"]
    counts["selected_completed_offline"] = counts["selected_completed_analyses"] - counts["completed_scout"]
    counts["substantive_offline"] = analyzers["agenttrace_heuristics_v1"] + analyzers["regex_v1"]
    counts["demo_plugin"] = analyzers["example_kickstart"]
    connection = sqlite3.connect((DATASET / manifest["database"]).as_uri() + "?mode=ro", uri=True)
    try:
        counts["historical_runs"] = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        require(connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == len(traces),
                "Database trace count mismatch")
    finally:
        connection.close()
    require(sum(row["count"] for row in manifest["history_counts"]) == counts["historical_runs"],
            "Historical run counts mismatch")
    for name, count in manifest["counts"].items():
        require(counts[name] == count, f"Manifest count mismatch: {name}")
    require(len(traces) == len(indexed) == len(LABELS), "Incomplete report inventory")
    summary = {
        "report_date": "2026-10-16",
        "data_commit": DATA_COMMIT,
        "analysis_code_commit": manifest["analysis_code_commit"],
        "snapshot_exported_at": manifest["exported_at"],
        "selected_analysis_completed_range": [min(dates), max(dates)],
        "counts": dict(sorted(counts.items())),
        "selected_analyzers": dict(sorted(analyzers.items())),
        "historical_runs": manifest["history_counts"],
        "raw_scout_positive_judgments": dict(positives),
        "primary_message_types_including_task_operator_posts": dict(sorted(primary_types.items())),
        "scout_versions": [
            {"model": model, "analyzer_version": version, "prompt_version": prompt, "traces": count}
            for (model, version, prompt), count in sorted(versions.items())
        ],
        "sha256": {
            name: hashlib.sha256((DATASET / name).read_bytes()).hexdigest()
            for name in ("manifest.json", "agenttrace.sqlite3", "SHA256SUMS")
        },
        "traces": [{key: value for key, value in trace.items() if key != "_messages"} for trace in traces],
    }
    return summary, traces


def bar_chart(traces):
    rows = []
    for number, trace in enumerate(traces):
        y = 39 + number * 37
        agent_width = trace["agent_posts"] * 17
        operator_width = trace["operator_posts"] * 17
        total = trace["agent_posts"] + trace["operator_posts"]
        rows.append(
            f'<text x="0" y="{y + 14}">{escape(trace["ref"] + " " + trace["label"])}</text>'
            f'<rect x="260" y="{y}" width="{agent_width}" height="21" fill="#087f82"/>'
            f'<rect x="{260 + agent_width}" y="{y}" width="{operator_width}" height="21" fill="#dca548"/>'
            f'<text x="{270 + agent_width + operator_width}" y="{y + 15}">{total}</text>'
        )
    return (
        '<svg viewBox="0 0 600 395" role="img" aria-labelledby="volume-title volume-desc">'
        '<title id="volume-title">Visible posts per trace</title>'
        '<desc id="volume-desc">59 agent posts and 11 task or operator posts across nine traces. '
        'The adjacent inventory table gives each count.</desc>'
        '<rect x="0" y="3" width="13" height="13" fill="#087f82"/>'
        '<text x="20" y="15">Agent</text>'
        '<rect x="110" y="3" width="13" height="13" fill="#dca548"/>'
        '<text x="130" y="15">Task / operator</text>'
        + "".join(rows) + "</svg>"
    )


def fragments(summary, traces):
    counts = summary["counts"]
    cards = "".join(
        f'<div class="stat"><strong>{counts[key]}</strong><span>{label}</span></div>'
        for key, label in (
            ("traces", "archived traces"),
            ("visible_posts", "visible posts: 59 agent + 11 task/operator"),
            ("completed_scout", "completed Scout runs"),
            ("collaboration_judgments", "category judgments, not failures"),
        )
    )
    inventory, matrix, registry = [], [], []
    for trace in traces:
        reference = link("#registry-" + trace["ref"], trace["ref"])
        inventory.append(
            f'<tr><td>{reference}</td><td>{escape(trace["label"])}</td>'
            f'<td>{trace["agent_posts"]} / {trace["operator_posts"]}</td></tr>'
        )
        cells = []
        by_category = {finding["category"]: finding for finding in trace["findings"]}
        for category in CATEGORIES:
            found = by_category[category]["found"]
            if trace["condition"] == "Solo":
                require(not found, "Solo raw labels changed; revisit presentation")
                text, css = "N/A (raw: no)", "unobserved"
            elif trace["agent_posts"] == 0:
                require(not found, "Task-only raw labels changed; revisit presentation")
                text, css = "Unknown (raw: no)", "unobserved"
            else:
                text, css = ("Flag", "flag") if found else ("No flag", "no-flag")
            cells.append(f'<td class="{css}">{text}</td>')
        matrix.append(
            f'<tr><td>{reference} {escape(trace["label"])}</td>'
            + "".join(cells) + "</tr>"
        )
        run_links = ", ".join(
            source_link(record["file"], {
                "agenttrace_heuristics_v1": "metrics",
                "regex_v1": "regex",
                "example_kickstart": "demo",
                "scout_collaboration_v1": "Scout",
            }[record["analyzer"]])
            for record in trace["selected_runs"]
        )
        registry.append(
            f'<tr id="registry-{trace["ref"]}"><td><b>{trace["ref"]}</b><br>'
            f'{escape(trace["slug"])}</td><td><code>{escape(trace["trace_id"])}</code><br>'
            + source_link(trace["source_file"], "snapshot") + " / "
            + source_link(trace["transcript_file"], "transcript") + " / "
            + link(trace["url"], "SharedNet")
            + f'</td><td>{run_links}<br><code title="{escape(trace["scout_run_id"], quote=True)}">'
            + escape(trace["scout_run_id"]) + "</code></td></tr>"
        )

    ownership = traces[1]
    cards_evidence = []
    for number, (label, quote) in OWNERSHIP_QUOTES.items():
        message = ownership["_messages"][number]
        require(quote in message["text"], f"Unfaithful quote at E2 #{number}")
        stamp = datetime.fromisoformat(message["timestamp"].replace("Z", "+00:00"))
        cards_evidence.append(
            f'<div class="evidence"><div class="eyebrow">{escape(label)}</div>'
            f'<blockquote>{escape(quote)}</blockquote><p>'
            f'{message_link(ownership, number)} &middot; {escape(message["sender"])}'
            f' &middot; {stamp.strftime("%H:%M:%S.%f")[:-3]} UTC</p></div>'
        )
    later = ownership["_messages"][17]["timestamp"]
    restored = ownership["_messages"][16]["timestamp"]
    seconds = (
        datetime.fromisoformat(later.replace("Z", "+00:00"))
        - datetime.fromisoformat(restored.replace("Z", "+00:00"))
    ).total_seconds()
    require(seconds == 6.141, "Ownership timeline changed")

    metrics = []
    for trace in traces[:3]:
        metrics.append(
            f'<tr><td>{trace["ref"]} {escape(trace["label"])}</td>'
            f'<td>{trace["all_post_p95_words"]:,}</td>'
            f'<td>{trace["agent_only_p95_words"]}</td><td>'
            + source_link(trace["report_file"], "all posts") + " / "
            + source_link(trace["agent_metrics_file"], "agent only") + "</td></tr>"
        )
    history = "".join(
        f'<tr><td><code>{escape(row["analyzer"])}</code></td><td>{escape(row["status"])}</td>'
        f'<td>{row["count"]}</td></tr>'
        for row in summary["historical_runs"]
    )
    versions = "".join(
        f'<tr><td>{escape(row["analyzer_version"])}</td><td>{escape(row["prompt_version"])}</td>'
        f'<td>{row["traces"]}</td></tr>'
        for row in summary["scout_versions"]
    )
    types = "".join(
        f'<tr><td>{label.replace("_", " ")}</td><td>{count}</td></tr>'
        for label, count in sorted(
            summary["primary_message_types_including_task_operator_posts"].items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    evidence = "".join(
        f'<tr><td><b>{trace["ref"]}</b></td><td>{escape(trace["observation"])}</td>'
        f'<td>{refs(trace, trace["evidence_messages"])}</td></tr>'
        for trace in traces
    )
    raw_totals = " / ".join(
        f'{summary["raw_scout_positive_judgments"][category]} of {counts["traces"]}'
        for category in CATEGORIES
    )
    return {
        "SUMMARY_CARDS": cards,
        "INVENTORY_ROWS": "".join(inventory),
        "POSTS_CHART": bar_chart(traces),
        "MATRIX_ROWS": "".join(matrix),
        "RAW_TOTALS": raw_totals,
        "OWNERSHIP_EVIDENCE": "".join(cards_evidence),
        "ARITHMETIC_REFS": refs(traces[5], (2, 3, 4, 5, 6)),
        "ARITHMETIC_SOLO_REF": message_link(traces[4], 2),
        "GPQA_REFS": refs(traces[8], (2, 5, 6, 7, 8, 10, 11, 12, 13)),
        "GPQA_SOLO_REF": message_link(traces[7], 2),
        "REGISTRY_ROWS": "".join(registry),
        "METRIC_ROWS": "".join(metrics),
        "VERSION_ROWS": versions,
        "HISTORY_ROWS": history,
        "TYPE_ROWS": types,
        "EVIDENCE_ROWS": evidence,
        "TARGET_TRUNCATED_COUNT": str(counts["messages_over_8000_characters"]),
        "CANDIDATE_TEXT_TRUNCATED_COUNT": str(counts["messages_over_2000_characters"]),
        "CANDIDATE_COUNT": str(counts["candidate_messages"]),
        "COUNT_TRUNCATED": str(counts["candidate_count_truncated_traces"]),
        "MANIFEST_SHA256": summary["sha256"]["manifest.json"],
        "DATABASE_SHA256": summary["sha256"]["agenttrace.sqlite3"],
        "SELECTED_DATES": (
            summary["selected_analysis_completed_range"][0][:10] + " to "
            + summary["selected_analysis_completed_range"][1][:10]
        ),
        "DATA_COMMIT": DATA_COMMIT,
        "CODE_COMMIT": summary["analysis_code_commit"],
        "SOURCE_PREFIX": GITHUB,
    }


def outputs():
    summary, traces = collect()
    rendered = (HERE / "template.html").read_text(encoding="utf-8")
    replacements = fragments(summary, traces)
    tokens = set(re.findall(r"\{\{([A-Z_0-9]+)\}\}", rendered))
    require(tokens == replacements.keys(), "Unknown or unused template substitutions")
    for name, value in replacements.items():
        rendered = rendered.replace("{{" + name + "}}", value)
    return {
        "index.html": rendered,
        "summary.json": json.dumps(summary, indent=2, ensure_ascii=True) + "\n",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on stale generated HTML or summary")
    args = parser.parse_args()
    for filename, content in outputs().items():
        path = HERE / filename
        if args.check:
            require(path.read_text(encoding="utf-8") == content, f"Stale report: {filename}")
        else:
            path.write_text(content, encoding="utf-8")
    print("Report and summary verified." if args.check else "Built index.html and summary.json; no model calls.")


if __name__ == "__main__":
    main()
