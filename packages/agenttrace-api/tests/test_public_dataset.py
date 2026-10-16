import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from fastapi.testclient import TestClient
import pytest

from agenttrace.api import create_app


DATASET = Path(__file__).resolve().parents[3] / "data" / "teammate-traces"
MANIFEST = json.loads((DATASET / "manifest.json").read_text())


@pytest.fixture
def restored_dataset(tmp_path):
    directory = tmp_path / "restored"
    directory.mkdir()
    shutil.copyfile(DATASET / "agenttrace.sqlite3", directory / "agenttrace.sqlite3")
    shutil.copytree(DATASET / "runs", directory / "runs")
    return directory


def test_public_snapshot_checksums_and_integrity():
    checksummed = set()
    for line in (DATASET / "SHA256SUMS").read_text().splitlines():
        checksum, relative = line.split("  ", 1)
        path = DATASET / relative
        assert path.resolve().is_relative_to(DATASET.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum, relative
        checksummed.add(relative)
    assert checksummed == {
        str(path.relative_to(DATASET))
        for path in DATASET.rglob("*")
        if path.is_file() and path.name not in {"README.md", "SHA256SUMS"}
    }
    connection = sqlite3.connect(
        (DATASET / "agenttrace.sqlite3").as_uri() + "?mode=ro", uri=True
    )
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == MANIFEST["counts"]["historical_runs"]
    finally:
        connection.close()


def test_restore_loads_every_saved_trace_and_selected_run(restored_dataset, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    async def forbidden(*args, **kwargs):
        pytest.fail("Loading the public snapshot must not run model analysis.")

    index = json.loads((DATASET / "batch" / "index.json").read_text())
    selected = []
    history = 0
    messages = 0
    with TestClient(create_app(data_dir=restored_dataset, scout_runner=forbidden)) as client:
        for trace in index["traces"]:
            response = client.get(f"/api/traces/{trace['trace_id']}")
            assert response.status_code == 200
            report = response.json()
            assert report["traceId"] == trace["trace_id"]
            assert report["analyses"]["scout_collaboration_v1"]["status"] == "completed"
            messages += len(report["messages"])
            response = client.get(f"/api/traces/{trace['trace_id']}/analyses")
            assert response.status_code == 200
            history += len(response.json())
            for record in trace["analyses"]:
                if record["status"] == "unavailable":
                    assert record["analyzer"] == "facts_v1"
                    continue
                assert record["status"] == "completed"
                response = client.get(f"/api/analysis-runs/{record['run_id']}")
                assert response.status_code == 200
                assert response.json() == json.loads((DATASET / "batch" / record["file"]).read_text())
                selected.append(record["run_id"])
    assert messages == 70
    assert len(set(selected)) == 36
    assert history == MANIFEST["counts"]["historical_runs"]


def test_restored_scout_results_replay_without_generation(restored_dataset, monkeypatch):
    pytest.importorskip("inspect_scout")
    from inspect_scout import scan_results_df
    from agenttrace.scout.viewer import export_saved_run

    async def forbidden(*args, **kwargs):
        pytest.fail("Restored native Scout exports must never call a model.")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("inspect_ai.model.Model.generate", forbidden)
    annotations = 0
    findings = 0
    with TestClient(create_app(data_dir=restored_dataset)) as client:
        for trace in MANIFEST["traces"]:
            report = client.get(f"/api/traces/{trace['trace_id']}").json()
            analysis = report["analyses"]["scout_collaboration_v1"]
            exported = export_saved_run(report, analysis, restored_dataset / "scout-view")
            native = scan_results_df(exported["location"])
            assert native.complete and not native.errors
            assert native.spec.metadata["original_provenance"] == analysis["provenance"]
            for frame in native.scanners.values():
                assert set(frame.transcript_id) == {trace["trace_id"]}
                assert (frame.scan_total_tokens.fillna(0) == 0).all()
            annotation_rows = native.scanners["saved_message_annotations"]
            finding_rows = native.scanners["saved_collaboration_findings"]
            assert list(annotation_rows.value) == [row["primary_type"] for row in analysis["output"]["annotations"]]
            assert list(finding_rows.value) == [row["found"] for row in analysis["output"]["findings"]]
            annotations += len(annotation_rows)
            findings += len(finding_rows)
    assert annotations == 70
    assert findings == 27
