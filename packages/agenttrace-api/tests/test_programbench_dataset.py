from collections import Counter
from html.parser import HTMLParser
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3

from commsfail import run
from commsfail.sources import sharednet
from fastapi.testclient import TestClient
import pytest

from agenttrace.api import create_app
from agenttrace.view_model import build_view_model


ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data/programbench-pr10"
OLD = ROOT / "data/teammate-traces"
REPORT = ROOT / "reports/2026-10-17-programbench"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_snapshot_checksums_source_manifests_and_database():
    checksummed = set()
    for line in (DATA / "SHA256SUMS").read_text().splitlines():
        checksum, relative = line.split("  ", 1)
        path = DATA / relative
        assert path.resolve().is_relative_to(DATA.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum, relative
        checksummed.add(relative)
    assert checksummed == {
        str(path.relative_to(DATA)) for path in DATA.rglob("*")
        if path.is_file() and path not in {DATA / "README.md", DATA / "SHA256SUMS"}
    }
    files = 0
    size = 0
    for manifest in (DATA / "sources").glob("*/manifest.json"):
        for item in read(manifest)["files"]:
            raw = (manifest.parent / item["path"]).read_bytes()
            assert len(raw) == item["bytes"]
            assert hashlib.sha256(raw).hexdigest() == item["sha256"]
            files += 1
            size += len(raw)
    assert (files, size) == (255, 5_446_720)
    with sqlite3.connect((DATA / "agenttrace.sqlite3").as_uri() + "?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == 12
        rows = [json.loads(row[0]) for row in connection.execute("SELECT content FROM runs")]
    assert Counter(row["status"] for row in rows) == {"completed": 60, "failed": 8}
    failures = {row["id"]: row for row in rows if row["status"] == "failed"}
    assert {path.stem for path in (DATA / "history").glob("run_*.json")} == set(failures)
    for identifier, row in failures.items():
        assert read(DATA / "history" / f"{identifier}.json") == row
    assert not (DATA / "scout-view").exists()
    manifest = read(DATA / "manifest.json")
    assert hashlib.sha256((ROOT / "packages/commsfail/commsfail/sources/sharednet.py").read_bytes()).hexdigest() == manifest["parser_sha256"]


def test_all_raw_commands_and_posts_are_retained_and_offline_results_reproduce():
    indexed = {row["trace_id"]: row for row in read(DATA / "batch/index.json")["traces"]}
    with sqlite3.connect((DATA / "agenttrace.sqlite3").as_uri() + "?mode=ro", uri=True) as connection:
        canonical = {identifier: json.loads(content) for identifier, content in connection.execute("SELECT id, content FROM traces")}
    totals = Counter()
    for item in read(DATA / "manifest.json")["traces"]:
        source = DATA / item["source"]
        trace = sharednet.load(source)
        posts = sharednet.agent_posts(trace)
        assert set(sharednet.post_ops(trace)) == {post["seq"] for post in posts}
        assert len(posts) == item["agent_posts"]
        raw_commands = Counter()
        for path in source.glob("agents/*/turn-*.jsonl"):
            turn = int(path.stem.removeprefix("turn-"))
            for line in path.read_text().split("\n"):
                if not line.strip():
                    continue
                event = json.loads(line)
                record = event.get("item") or {}
                if event.get("type") == "item.completed" and record.get("type") == "command_execution":
                    raw_commands[(path.parent.name, turn, record.get("command"), record.get("exit_code"),
                                  (record.get("aggregated_output") or "")[-500:])] += 1
        parsed = Counter(
            (command["seat"], command["turn"], command.get("command"), command.get("exit_code"), command["output"])
            for command in sharednet.commands(trace)
        )
        assert raw_commands == parsed
        assert sum(parsed.values()) == item["commands"]
        entry = indexed[item["trace_id"]]
        report = read(DATA / "batch" / entry["report_file"])
        assert build_view_model(trace)["metrics"] == report["metrics"]
        saved = canonical[item["trace_id"]]
        assert {key: value for key, value in trace.to_dict().items() if key != "source"} == {
            key: value for key, value in saved.items() if key != "source"
        }
        trace.source = saved["source"]
        for record in entry["analyses"]:
            if record["analyzer"] != "scout_collaboration_v1":
                selected = read(DATA / "batch" / record["file"])
                assert run(record["analyzer"], trace)["output"] == selected["output"]["output"]
        totals.update(posts=len(trace.posts), agents=len(posts), commands=sum(parsed.values()),
                      operations=sum(len(ops) for ops in trace.ops.values()))
    assert totals == {"posts": 618, "agents": 602, "commands": 1874, "operations": 2322}


def test_combined_restore_and_failure_safety(tmp_path):
    restore = load_module("restore_snapshots", ROOT / "tools/restore_results.py").restore
    output = tmp_path / "working"
    restore([OLD, DATA], output)
    before = (output / "agenttrace.sqlite3").read_bytes()
    with sqlite3.connect(output / "agenttrace.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == 21
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 117
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    with pytest.raises(ValueError, match="overwrite"):
        restore([DATA], output)
    assert (output / "agenttrace.sqlite3").read_bytes() == before
    duplicate = tmp_path / "duplicate"
    with pytest.raises(sqlite3.IntegrityError):
        restore([DATA, DATA], duplicate)
    assert not duplicate.exists()
    with pytest.raises(ValueError, match="no agenttrace.sqlite3"):
        restore([tmp_path / "missing"], duplicate)
    assert not duplicate.exists()
    assert not list(tmp_path.glob(".restore-*"))


def test_saved_selection_and_all_native_replays_are_model_free(tmp_path, monkeypatch):
    pytest.importorskip("inspect_scout")
    from inspect_scout import scan_results_df
    from agenttrace.scout.adapter import transcript_from_report
    from agenttrace.scout.viewer import export_saved_run, saved_results

    async def forbidden(*args, **kwargs):
        pytest.fail("Reading/restoring/replaying frozen results must not call a model.")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("inspect_ai.model.Model.generate", forbidden)
    restored = tmp_path / "restored"
    load_module("restore_replay", ROOT / "tools/restore_results.py").restore([DATA], restored)
    totals = Counter()
    with TestClient(create_app(data_dir=restored, scout_runner=forbidden)) as client:
        for item in read(DATA / "batch/index.json")["traces"]:
            response = client.get(f"/api/traces/{item['trace_id']}")
            assert response.status_code == 200
            report = response.json()
            assert len(report["messages"]) == len({m["index"] for m in report["messages"]})
            for record in item["analyses"]:
                response = client.get(f"/api/analysis-runs/{record['run_id']}")
                assert response.status_code == 200
                assert response.json() == read(DATA / "batch" / record["file"])
                totals["analyses"] += 1
            analysis = report["analyses"]["scout_collaboration_v1"]
            transcript = transcript_from_report(report)
            for message in transcript.messages:
                message.id = f"{item['trace_id']}_m{message.metadata['sequence']}"
            _, findings = saved_results(transcript, analysis["output"])
            for result, original in zip(findings, analysis["output"]["findings"]):
                assert {ref.id for ref in result.references} == {
                    f"{item['trace_id']}_m{number}" for number in original["message_numbers"]
                }
            exported = export_saved_run(report, analysis, restored / "scout-view")
            native = scan_results_df(exported["location"])
            assert native.complete and not native.errors
            assert native.spec.metadata["original_provenance"] == analysis["provenance"]
            for frame in native.scanners.values():
                assert set(frame.transcript_id) == {item["trace_id"]}
                assert (frame.scan_total_tokens.fillna(0) == 0).all()
            annotations = native.scanners["saved_message_annotations"]
            findings = native.scanners["saved_collaboration_findings"]
            assert list(annotations.value) == [row["primary_type"] for row in analysis["output"]["annotations"]]
            assert list(findings.value) == [row["found"] for row in analysis["output"]["findings"]]
            totals.update(annotations=len(annotations), findings=len(findings))
    assert totals == {"analyses": 60, "annotations": 602, "findings": 36}


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.sheets = 0
        self.external_assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs["href"])
        if tag == "article" and attrs.get("class") == "sheet":
            self.sheets += 1
        if ("src" in attrs and not attrs["src"].startswith("data:")) or (
            tag == "link" and not attrs.get("href", "").startswith("data:")
        ):
            self.external_assets.append(attrs)


def test_addendum_is_deterministic_auditable_and_portable():
    builder = load_module("programbench_report", REPORT / "build_report.py")
    generated = builder.outputs()
    assert generated == builder.outputs()
    for filename, content in generated.items():
        assert (REPORT / filename).read_text(encoding="utf-8") == content
    summary = read(REPORT / "summary.json")
    assert summary["counts"] == {
        "traces": 12, "raw_posts": 618, "agent_posts": 602, "turn_logs": 195, "operations": 2322,
        "commands": 1874, "annotations": 602, "judgments": 36, "candidate_messages": 602,
        "candidate_count_truncated": 0, "messages_over_2000_chars": 0, "messages_over_8000_chars": 0,
        "fact_flags": 4, "selected_analyses": 60, "substantive_offline": 36, "demo": 12,
        "scout_completed": 12, "historical_runs": 68, "failed_attempts": 8, "citation_mismatch_records": 20,
    }
    assert sum(len(audit["seqs"]) for audit in summary["audits"]) == 4
    assert sum(sum(a["display_citations_missing_from_structured_turns"] for a in row["scout_citation_audit"])
               for row in summary["traces"]) == 20
    assert summary["raw_scout_positive_judgments"] == dict.fromkeys(builder.CATEGORIES, 12)
    assert [(v["analyzer"], v["prompt"], v["traces"]) for v in summary["scout_versions"]] == [
        ("2.1.0", "3", 7), ("2.1.1", "4", 4), ("2.1.4", "7", 1),
    ]
    parser = ReportParser()
    parser.feed(generated["index.html"])
    assert parser.sheets == 6
    assert len(parser.ids) == len(set(parser.ids))
    assert not parser.external_assets
    for url in parser.links:
        if url.startswith("#"):
            assert url[1:] in parser.ids
        elif url.startswith(builder.PUBLIC):
            assert (ROOT / url[len(builder.PUBLIC):].split("#", 1)[0]).exists(), url
        elif url.startswith(builder.UPSTREAM):
            relative = url[len(builder.UPSTREAM):].split("#", 1)[0]
            assert (DATA / "sources" / relative).is_file(), url
    assert "{{" not in generated["index.html"]
    assert "/Users/" not in generated["index.html"]
    pdf = (REPORT / "progress-addendum.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-")
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == 6
    assert not re.search(rb"/URI\s*\([^)]*(?:127\.0\.0\.1|file:)[^)]*\)", pdf)
    combined = ReportParser()
    combined.feed((DATA / "batch/all-cohorts.html").read_text())
    local = [url for url in combined.links if url.startswith("http://127.0.0.1:3001/")]
    assert len(local) == 21 + 96
    assert len(set(local)) == len(local)
