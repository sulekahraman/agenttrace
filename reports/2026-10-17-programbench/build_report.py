"""Build the ProgramBench addendum from frozen evidence, without model calls."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from statistics import mean

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data/programbench-pr10"
REVISION = "913ad1805642a38e5248d67e5d8c3b83c48b51b5"
UPSTREAM = f"https://github.com/xisen-w/commsfail/blob/{REVISION}/sample/"
PUBLIC = "https://github.com/sulekahraman/agenttrace/blob/main/"
CATEGORIES = ("duplicated_work", "weak_handoff", "unintegrated_information")
AUDITS = [
    {"slug": "xsv-n3-round3", "seqs": [48], "fact": "success_after_failure",
     "assessment": "not_confirmed_shell_status_ambiguity",
     "observation": "The cited command is a smoke-test reporting loop ending in a conditional echo. "
                    "Its exit status can be 1 when the last condition is false. Its full output is empty; "
                    "post #47 reports no crashes. This is not evidence of a hidden-test failure."},
    {"slug": "yj-n2-round1", "seqs": [31], "fact": "private_contradiction",
     "assessment": "unsupported_by_cited_evidence",
     "observation": "The cited same-turn text announces a plan to check error behavior, not a failed result. "
                    "The actual final harness message is DONE. The broad error-keyword rule mistakes a test plan for contradiction."},
    {"slug": "yj-n4-round1", "seqs": [68, 69], "fact": "private_contradiction",
     "assessment": "unsupported_by_cited_evidence",
     "observation": "The cited harness text describes expected exit-code-1 validation for an invalid -k "
                    "configuration, alongside successful builds. Mentioning the expected error is not a "
                    "contradiction of completion. These are two rule flags, not two verified failures."},
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def link(url, label):
    return f'<a href="{escape(url, quote=True)}">{escape(str(label))}</a>'


def source_url(row, filename="room.ndjson", line=None):
    url = UPSTREAM + row["study"] + "/" + row["configuration"] + "/record-run/" + filename
    return url + (f"#L{line}" if line else "")


def collect():
    manifest = read(DATA / "manifest.json")
    require(manifest["source"]["commit"] == REVISION, "Changed upstream snapshot")
    index = read(DATA / "batch/index.json")
    indexed = {entry["trace_id"]: entry for entry in index["traces"]}
    counts, analyzers, positives, facts, versions = Counter(), Counter(), Counter(), Counter(), Counter()
    rows, run_ids = [], set()
    for position, item in enumerate(manifest["traces"], 1):
        source = DATA / item["source"]
        raw = [json.loads(line) for line in (source / "room.ndjson").read_text().split("\n") if line.strip()]
        require([post["sequence"] for post in raw] == list(range(1, len(raw) + 1)), "Source line/sequence mismatch")
        episode = read(source / "episode.json")
        entry = indexed[item["trace_id"]]
        require(entry["status"] == "completed", f"Incomplete trace: {item['slug']}")
        report = read(DATA / "batch" / entry["report_file"])
        require(report["traceId"] == item["trace_id"], "Report trace mismatch")
        messages = {message["index"]: message for message in report["messages"]}
        selected = {}
        records = []
        for record in entry["analyses"]:
            analysis = read(DATA / "batch" / record["file"])
            name = record["analyzer"]
            require(analysis["status"] == record["status"] == "completed", "Incomplete selected analysis")
            require(analysis["id"] == record["run_id"] and analysis["trace_id"] == item["trace_id"], "Analysis identity mismatch")
            require(analysis == report["analyses"][name], "Report/selected analysis mismatch")
            require(analysis["id"] not in run_ids, "Duplicate analysis ID")
            run_ids.add(analysis["id"])
            selected[name] = analysis
            analyzers[name] += 1
            records.append({"analyzer": name, "run_id": analysis["id"],
                            "file": "batch/" + record["file"], "provenance": analysis["provenance"],
                            "version": analysis["analyzer"]["version"]})
        require(set(selected) == {"facts_v1", "regex_v1", "example_kickstart",
                                  "agenttrace_heuristics_v1", "scout_collaboration_v1"}, "Unexpected analyzer set")
        scout = selected["scout_collaboration_v1"]
        output = scout["output"]
        require({a["message_number"] for a in output["annotations"]} == set(messages), "Annotation coverage mismatch")
        require(len(output["annotations"]) == len(messages) == item["agent_posts"], "Visible-message mismatch")
        prompt = (DATA / "runs" / scout["id"] / "collaboration.prompt.txt").read_text()
        display_map = {
            int(display): int(original)
            for display, original in re.findall(
                r"^\[M(\d+)\] [^\n]*\nAgentTrace turn #(\d+);", prompt, re.MULTILINE
            )
        }
        require(set(display_map.values()) <= set(messages)
                and len(display_map) == output["coverage"]["candidate_messages"], "Candidate map mismatch")
        citation_audit = []
        require({f["category"] for f in output["findings"]} == set(CATEGORIES)
                and len(output["findings"]) == 3, "Judgment category mismatch")
        for finding in output["findings"]:
            require(type(finding["found"]) is bool, "Non-boolean judgment")
            require(set(finding["message_numbers"]) <= set(messages), "Invalid evidence")
            require(not finding["found"] or finding["message_numbers"], "Uncited positive judgment")
            positives[finding["category"]] += int(finding["found"])
            labels = sorted({int(n) for n in re.findall(r"\[M(\d+)\]", finding["explanation"])})
            mapped = sorted({display_map[n] for n in labels if n in display_map})
            mismatch = (any(n not in display_map for n in labels)
                        or not set(mapped) <= set(finding["message_numbers"]))
            counts["citation_mismatch_records"] += int(mismatch)
            citation_audit.append({"category": finding["category"], "display_labels": labels,
                                   "mapped_original_turns": mapped, "structured_turns": finding["message_numbers"],
                                   "display_citations_missing_from_structured_turns": mismatch})
        fact_output = selected["facts_v1"]["output"]["output"]
        facts.update(fact_output["counts"])
        parse = lambda text: datetime.fromisoformat(text.replace("Z", "+00:00"))
        runtime = (parse(episode["runner"]["ended_at"]) - parse(episode["runner"]["started_at"])).total_seconds()
        require(episode["totals"]["tokens"] == sum(a["tokens"] for a in episode["agents"]), "Runner token mismatch")
        require(episode["consensus"] is True and episode["ended_by"]["trigger"] == "said DONE", "Changed stop condition")
        require(not (source / "checks.ndjson").read_bytes(), "Unexpected runner checks")
        versions[(scout["analyzer"]["version"], scout["provenance"]["prompt_version"],
                  scout["provenance"]["model"])] += 1
        coverage = output["coverage"]
        counts.update(traces=1, raw_posts=len(raw), agent_posts=len(messages),
                      turn_logs=item["turn_log_files"], operations=item["operations"], commands=item["commands"],
                      annotations=len(output["annotations"]), judgments=3, candidate_messages=coverage["candidate_messages"],
                      candidate_count_truncated=int(coverage["truncated"]),
                      messages_over_2000_chars=sum(len(m["text"]) > 2000 for m in messages.values()),
                      messages_over_8000_chars=sum(len(m["text"]) > 8000 for m in messages.values()),
                      fact_flags=len(fact_output["findings"]))
        rows.append({**item, "ref": f"N{position}", "runtime_seconds": runtime,
                     "runner_tokens": episode["totals"]["tokens"], "runner_cached_tokens": episode["totals"]["cached_tokens"],
                     "experiment_models": sorted({agent["model"] for agent in episode["agents"]}),
                     "termination": episode["ended_by"], "evaluation_status": "unavailable",
                     "fact_findings": fact_output["findings"], "scout_findings": output["findings"],
                     "scout_citation_audit": citation_audit,
                     "scout_run_id": scout["id"], "scout_coverage": coverage, "selected_runs": records,
                     "agent_only_p95_words": report["metrics"]["p95WordsPerMessage"]})
    require(len(rows) == len(indexed) == 12, "Unexpected cohort size")
    actual = {(row["slug"], flag["seq"], flag["fact"]) for row in rows for flag in row["fact_findings"]}
    expected = {(audit["slug"], seq, audit["fact"]) for audit in AUDITS for seq in audit["seqs"]}
    require(actual == expected, "Changed flags: revisit the qualitative audit")
    with sqlite3.connect((DATA / "agenttrace.sqlite3").as_uri() + "?mode=ro", uri=True) as connection:
        require(connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == 12, "Snapshot cohort mismatch")
        history = Counter()
        for (content,) in connection.execute("SELECT content FROM runs"):
            analysis = json.loads(content)
            history[analysis["status"]] += 1
    counts.update(selected_analyses=sum(analyzers.values()), substantive_offline=36, demo=12, scout_completed=12,
                  historical_runs=sum(history.values()), failed_attempts=history["failed"])
    groups = defaultdict(list)
    for row in rows:
        groups[(row["study"].split("-")[0], row["seats"])].append(row)
    grouped = [{"task": task, "agents": seats, "runs": len(items),
                "mean_raw_posts": mean(x["posts"] for x in items),
                "mean_runtime_seconds": mean(x["runtime_seconds"] for x in items),
                "mean_runner_tokens": mean(x["runner_tokens"] for x in items)}
               for (task, seats), items in sorted(groups.items())]
    return {
        "report_date": "2026-10-17", "source": manifest["source"],
        "reader_sha256": manifest["parser_sha256"], "counts": dict(counts),
        "selected_analyzers": dict(analyzers), "raw_scout_positive_judgments": dict(positives),
        "facts_v1_counts": dict(facts), "history_status": dict(history),
        "scout_versions": [{"analyzer": a, "prompt": p, "model": m, "traces": n}
                           for (a, p, m), n in sorted(versions.items())],
        "groups": grouped, "audits": AUDITS, "traces": rows,
        "combined_inventory": {"traces": 21, "raw_posts": 688, "agent_posts": 661,
                               "selected_analyses": 96, "scout_annotations": 672},
        "dataset_hashes": {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest()
                           for name in ("manifest.json", "agenttrace.sqlite3", "SHA256SUMS")},
    }


def render(summary):
    rows = summary["traces"]
    grouped = "".join(
        f"<tr><td>{r['task']}</td><td>{r['agents']}</td><td>{r['runs']}</td>"
        f"<td>{r['mean_raw_posts']:.1f}</td><td>{r['mean_runtime_seconds']/60:.2f}</td>"
        f"<td>{r['mean_runner_tokens']:,.0f}</td></tr>" for r in summary["groups"]
    )
    matrix, registry = [], []
    for row in rows:
        findings = {f["category"]: f["found"] for f in row["scout_findings"]}
        judgments = "".join(f'<td class="{"yes" if findings[c] else "no"}">{"Yes" if findings[c] else "No"}</td>' for c in CATEGORIES)
        label = row["slug"]
        matrix.append(f"<tr><td>{link(source_url(row), row['ref'] + ' ' + label)}</td>"
                      f"<td>{row['seats']}</td><td>{row['posts']}/{row['agent_posts']}</td>"
                      f"<td>{row['runtime_seconds']/60:.2f}</td><td>{row['runner_tokens']:,}</td>"
                      f"<td>{len(row['fact_findings'])}</td>{judgments}</tr>")
        registry.append(f"<tr><td>{row['ref']} {escape(label)}</td><td><code>{row['trace_id']}</code></td>"
                        f"<td><code>{row['scout_run_id']}</code></td></tr>")
    audits = []
    by_slug = {row["slug"]: row for row in rows}
    for audit in AUDITS:
        row = by_slug[audit["slug"]]
        refs = ", ".join(link(source_url(row, line=seq), f"#{seq}") for seq in audit["seqs"])
        audits.append(f"<tr><td>{row['ref']} {refs}<br><code>{audit['fact']}</code></td>"
                      f"<td>{escape(audit['observation'])}</td></tr>")
    versions = "; ".join(f"{v['traces']} runs: {v['analyzer']} / prompt {v['prompt']}" for v in summary["scout_versions"])
    replacements = {
        "GROUPS": grouped, "MATRIX": "".join(matrix), "AUDITS": "".join(audits),
        "REGISTRY": "".join(registry), "VERSIONS": escape(versions),
        "FAILED": str(summary["counts"]["failed_attempts"]),
        "POSITIVES": ", ".join(f"{c.replace('_', ' ')}: {summary['raw_scout_positive_judgments'][c]}/12" for c in CATEGORIES),
        "COVERAGE": (f"{summary['counts']['annotations']} annotations; {summary['counts']['candidate_messages']} "
                     f"candidate messages; {summary['counts']['candidate_count_truncated']} count-truncated traces. "
                     f"{summary['counts']['messages_over_2000_chars']} agent messages exceed 2,000 characters; "
                     f"{summary['counts']['messages_over_8000_chars']} exceed 8,000."),
        "HISTORY": str(summary["counts"]["historical_runs"]),
        "CITATION_MISMATCHES": str(summary["counts"]["citation_mismatch_records"]),
    }
    html = (HERE / "template.html").read_text(encoding="utf-8")
    for key, value in replacements.items():
        html = html.replace("{{" + key + "}}", value)
    require(not re.search(r"\{\{[A-Z_]+\}\}", html), "Unfilled report marker")
    return html


def outputs():
    summary = collect()
    return {"index.html": render(summary),
            "summary.json": json.dumps(summary, indent=2, ensure_ascii=False) + "\n"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, text in outputs().items():
        path = HERE / name
        if args.check:
            require(path.read_text(encoding="utf-8") == text, f"Stale output: {name}")
        else:
            path.write_text(text, encoding="utf-8")
    print("Addendum outputs verified." if args.check else "Generated HTML and JSON; re-export the PDF after changes.")


if __name__ == "__main__":
    main()
