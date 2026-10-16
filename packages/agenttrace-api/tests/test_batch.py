import argparse
import json

import pytest
from fastapi.testclient import TestClient

from agenttrace.api import create_app
from agenttrace.batch import local_server, positive, run_batch


def test_exports_offline_results_links_and_reuses_runs(client, share, tmp_path):
    entries = [{"name": "first", "source": {"type": "share_json", "value": share}}]
    result = run_batch(client, entries, tmp_path / "export", "http://127.0.0.1:3000")
    item = result["traces"][0]
    assert item["status"] == "completed"
    completed = [a for a in item["analyses"] if a["status"] == "completed"]
    assert {a["analyzer"] for a in completed} >= {"regex_v1", "agenttrace_heuristics_v1"}
    assert next(a for a in item["analyses"] if a["analyzer"] == "facts_v1")["status"] == "unavailable"
    assert all(a["reused"] for a in completed if a["analyzer"] in ("regex_v1", "agenttrace_heuristics_v1"))
    assert all(f"&run={a['run_id']}" in a["url"] for a in completed)
    assert json.loads((tmp_path / "export/index.json").read_text()) == result
    assert (tmp_path / "export/index.json").stat().st_mode & 0o077 == 0
    assert item["trace_id"] in (tmp_path / "export/links.html").read_text()
    again = run_batch(client, [{"trace_id": item["trace_id"]}], tmp_path / "again", "http://localhost:3000")
    assert {a.get("run_id") for a in again["traces"][0]["analyses"]} == {a.get("run_id") for a in item["analyses"]}
    assert len(client.get(f"/api/traces/{item['trace_id']}/analyses").json()) == len(completed)


def test_scout_setup_failure_is_explicit_and_does_not_enqueue(client, share, tmp_path):
    result = run_batch(client, [{"source": {"type": "share_json", "value": share}}],
                       tmp_path / "export", "http://localhost:3000", scout=True)
    item = result["traces"][0]
    assert item["status"] == "incomplete"
    scout = next(a for a in item["analyses"] if a["analyzer"] == "scout_collaboration_v1")
    assert scout["status"] == "blocked"
    assert not scout["setup"]["ready"]
    assert not any(a["analyzer"]["name"] == "scout_collaboration_v1"
                   for a in client.get(f"/api/traces/{item['trace_id']}/analyses").json())


def test_mock_scout_completes_and_is_not_repeated(share, tmp_path, monkeypatch):
    calls = []

    async def mock_scout(report, model, artifacts):
        calls.append(model)
        return {"findings": [], "coverage": {"annotated_messages": 3}}

    monkeypatch.setattr("agenttrace.api.scout_setup", lambda model: {"ready": True, "model": model})
    with TestClient(create_app(data_dir=tmp_path / "data", scout_runner=mock_scout)) as client:
        result = run_batch(client, [{"source": {"type": "share_json", "value": share}}],
                           tmp_path / "export", "http://localhost:3000", scout=True,
                           model="mockllm/model", poll_interval=0.01, wait_timeout=5)
        item = result["traces"][0]
        assert item["status"] == "completed"
        scout = next(a for a in item["analyses"] if a["analyzer"] == "scout_collaboration_v1")
        assert scout["status"] == "completed"
        exported = json.loads((tmp_path / "export" / scout["file"]).read_text())
        assert exported["output"]["coverage"]["annotated_messages"] == 3
        again = run_batch(client, [{"trace_id": item["trace_id"]}], tmp_path / "again",
                          "http://localhost:3000", scout=True, model="mockllm/model")
        assert again["traces"][0]["status"] == "completed"
        assert calls == ["mockllm/model"]
        run_batch(client, [{"trace_id": item["trace_id"]}], tmp_path / "rerun",
                  "http://localhost:3000", scout=True, model="mockllm/model",
                  rerun=True, poll_interval=0.01, wait_timeout=5)
        assert calls == ["mockllm/model", "mockllm/model"]


def test_ingestion_failure_does_not_hide_other_trace_results(client, share, tmp_path):
    result = run_batch(client, [
        {"trace_id": "trace_0000000000000000"},
        {"source": {"type": "share_json", "value": share}},
    ], tmp_path / "export", "http://localhost:3000")
    assert result["traces"][0]["status"] == "error"
    assert "404" in result["traces"][0]["error"]
    assert result["traces"][1]["status"] == "completed"


def test_scout_timeout_preserves_run_link(share, tmp_path, monkeypatch):
    import asyncio

    async def mock_scout(report, model, artifacts):
        await asyncio.sleep(10)

    monkeypatch.setattr("agenttrace.api.scout_setup", lambda model: {"ready": True, "model": model})
    with TestClient(create_app(data_dir=tmp_path / "data", scout_runner=mock_scout)) as client:
        result = run_batch(client, [{"source": {"type": "share_json", "value": share}}],
                           tmp_path / "export", "http://localhost:3000", scout=True,
                           wait_timeout=0.02, poll_interval=0.01)
        scout = next(a for a in result["traces"][0]["analyses"] if a["analyzer"] == "scout_collaboration_v1")
        assert scout["status"] == "error"
        assert "may still be running" in scout["error"]
        assert scout["run_id"] in scout["url"]


def test_scout_failure_is_exported_not_success(share, tmp_path, monkeypatch):
    async def mock_scout(report, model, artifacts):
        raise RuntimeError("Mock provider failure")

    monkeypatch.setattr("agenttrace.api.scout_setup", lambda model: {"ready": True, "model": model})
    with TestClient(create_app(data_dir=tmp_path / "data", scout_runner=mock_scout)) as client:
        result = run_batch(client, [{"source": {"type": "share_json", "value": share}}],
                           tmp_path / "export", "http://localhost:3000", scout=True,
                           poll_interval=0.01, wait_timeout=5)
        assert result["traces"][0]["status"] == "incomplete"
        scout = next(a for a in result["traces"][0]["analyses"] if a["analyzer"] == "scout_collaboration_v1")
        assert scout["status"] == "failed"
        assert scout["error"] == "Mock provider failure"


def test_different_active_scout_model_is_not_silently_reused(share, tmp_path, monkeypatch):
    import asyncio

    async def mock_scout(report, model, artifacts):
        await asyncio.sleep(10)

    monkeypatch.setattr("agenttrace.api.scout_setup", lambda model: {"ready": True, "model": model})
    with TestClient(create_app(data_dir=tmp_path / "data", scout_runner=mock_scout)) as client:
        report = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
        active = client.post(f"/api/traces/{report['traceId']}/analyses/scout_collaboration_v1",
                             json={"model": "mockllm/first"}).json()
        result = run_batch(client, [{"trace_id": report["traceId"]}], tmp_path / "export",
                           "http://localhost:3000", scout=True, model="mockllm/second")
        scout = next(a for a in result["traces"][0]["analyses"] if a["analyzer"] == "scout_collaboration_v1")
        assert scout["status"] == "blocked"
        assert "different model" in scout["reason"]
        assert scout["run_id"] == active["id"]


@pytest.mark.parametrize("value", ["https://example.com", "http://localhost:3000/api", "http://user@localhost"])
def test_rejects_nonlocal_servers(value):
    with pytest.raises(argparse.ArgumentTypeError):
        local_server(value)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_rejects_invalid_time_limits(value):
    with pytest.raises(argparse.ArgumentTypeError):
        positive(value)
