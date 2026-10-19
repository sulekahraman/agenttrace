import asyncio
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import validate

from agenttrace.api import DEFAULT_SCOUT_MODEL, SCOUT_PROMPT_VERSION, SCOUT_VERSION, create_app
from agenttrace.models import AnalysisRun
from agenttrace.store import Store


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_ingestion_and_analysis_contracts(client, trace_response):
    identifier = trace_response["traceId"]
    assert trace_response["metrics"]["totalMessages"] == 3
    assert set(trace_response["analyses"]) == {"regex_v1", "agenttrace_heuristics_v1"}
    for analysis in trace_response["analyses"].values():
        assert analysis["status"] == "completed", analysis
        validate(analysis, AnalysisRun.model_json_schema())
    assert len(client.get(f"/api/traces/{identifier}/analyses").json()) == 2
    assert client.get(f"/api/traces/{identifier}").json() == trace_response
    raw = client.get(f"/api/traces/{identifier}/raw").json()
    schema = Path(__file__).resolve().parents[1] / "agenttrace/schemas/trace.v1.json"
    validate(raw, json.loads(schema.read_text()))


def test_run_schema_matches_pydantic_contract():
    schema = Path(__file__).resolve().parents[1] / "agenttrace/schemas/analysis-run.v1.json"
    assert json.loads(schema.read_text()) == AnalysisRun.model_json_schema()


def test_oversized_body_is_rejected(client):
    response = client.post("/api/traces", content=b"x" * 5_000_001,
                           headers={"content-type": "application/json"})
    assert response.status_code == 413


def test_repeat_ingestion_reuses_trace_and_offline_results(client, share, trace_response):
    response = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}})
    assert response.json()["traceId"] == trace_response["traceId"]
    assert response.json()["analyses"] == trace_response["analyses"]
    share["messages"][0]["content"] += " Changed."
    changed = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}})
    assert changed.json()["traceId"] != trace_response["traceId"]


def test_persistence_across_api_restart(tmp_path, share):
    data = tmp_path / "data"
    with TestClient(create_app(data_dir=data)) as client:
        created = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
    with TestClient(create_app(data_dir=data)) as client:
        assert client.get(f"/api/traces/{created['traceId']}").json() == created


def test_model_and_trace_validation(client, trace_response):
    identifier = trace_response["traceId"]
    assert client.post("/api/traces/missing/analyses/scout_collaboration_v1", json={}).status_code == 404
    assert client.post(f"/api/traces/{identifier}/analyses/scout_collaboration_v1", json={"model": " "}).status_code == 422
    assert client.post(f"/api/traces/{identifier}/analyses/unknown", json={}).status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.post("/api/traces", json={}).status_code == 422
    assert client.post("/api/traces", json={"source": {"type": "local", "value": "/etc/passwd"}}).status_code == 400


def test_scout_default_and_override(client, monkeypatch):
    def selected_model():
        return next(item for item in client.get("/api/analyzers").json() if item["name"] == "scout_collaboration_v1")["default_model"]

    assert selected_model() == DEFAULT_SCOUT_MODEL
    monkeypatch.setenv("AGENTTRACE_SCOUT_MODEL", "mockllm/custom")
    assert selected_model() == "mockllm/custom"
    assert client.get("/api/scout/setup").json()["model"] == "mockllm/custom"
    monkeypatch.setenv("AGENTTRACE_SCOUT_MODEL", " ")
    assert selected_model() == DEFAULT_SCOUT_MODEL
    assert client.get("/api/scout/setup", params={"model": " "}).status_code == 422


def test_scout_missing_key_creates_no_run(client, trace_response, monkeypatch):
    monkeypatch.setattr("agenttrace.api.importlib.util.find_spec", lambda _: object())
    identifier = trace_response["traceId"]
    before = client.get(f"/api/traces/{identifier}/analyses").json()
    setup = client.get("/api/scout/setup").json()
    assert setup["ready"] is False
    assert setup["issues"] == [{"code": "openai_api_key_missing", "message": "OPENAI_API_KEY is not set in the API server's environment."}]
    response = client.post(f"/api/traces/{identifier}/analyses/scout_collaboration_v1", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "scout_setup_required"
    assert response.json()["detail"]["setup"] == setup
    assert client.get(f"/api/traces/{identifier}/analyses").json() == before
    monkeypatch.setenv("OPENAI_API_KEY", " ")
    assert client.get("/api/scout/setup").json()["ready"] is False
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key-not-a-real-credential")
    setup = client.get("/api/scout/setup").json()
    assert setup["ready"] is True
    assert "test-only-key-not-a-real-credential" not in json.dumps(setup)
    assert client.get("/api/scout/setup", params={"model": "mockllm/model"}).json()["ready"] is True


def test_scout_missing_package_creates_no_run(client, trace_response, monkeypatch):
    monkeypatch.setattr("agenttrace.api.importlib.util.find_spec", lambda _: None)
    identifier = trace_response["traceId"]
    response = client.post(f"/api/traces/{identifier}/analyses/scout_collaboration_v1", json={})
    assert response.status_code == 503
    setup = response.json()["detail"]["setup"]
    assert {issue["code"] for issue in setup["issues"]} == {"scout_not_installed", "openai_api_key_missing"}
    assert setup["install_command"] == 'python -m pip install -e "./packages/agenttrace-api[scout]"'
    assert setup["start_command"] == "agenttrace"
    assert len(client.get(f"/api/traces/{identifier}/analyses").json()) == 2


def test_default_scout_model_is_used_when_omitted(tmp_path, share, monkeypatch):
    monkeypatch.delenv("AGENTTRACE_SCOUT_MODEL", raising=False)
    async def fake_scout(report, model, artifacts):
        assert model == DEFAULT_SCOUT_MODEL
        return {"findings": []}

    with TestClient(create_app(data_dir=tmp_path, scout_runner=fake_scout)) as client:
        trace = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
        response = client.post(f"/api/traces/{trace['traceId']}/analyses/scout_collaboration_v1", json={})
        assert response.status_code == 202
        completed = wait_for_run(client, response.json()["id"])
        assert completed["status"] == "completed"
        assert completed["provenance"]["model"] == DEFAULT_SCOUT_MODEL
        assert completed["analyzer"]["version"] == SCOUT_VERSION == "2.2.0"
        assert completed["provenance"]["prompt_version"] == SCOUT_PROMPT_VERSION == "8"


def test_facts_requires_execution_logs(client, trace_response):
    identifier = trace_response["traceId"]
    catalog = client.get(f"/api/analyzers?trace_id={identifier}").json()
    facts = next(item for item in catalog if item["name"] == "facts_v1")
    assert facts["available"] is False
    assert facts["requires_ops"] is True
    assert "execution logs" in facts["unavailable_reason"]
    assert trace_response["analyzers"] == catalog
    before = client.get(f"/api/traces/{identifier}/analyses").json()
    response = client.post(f"/api/traces/{identifier}/analyses/facts_v1", json={})
    assert response.status_code == 422
    assert "Use regex_v1 instead" in response.json()["detail"]
    assert client.get(f"/api/traces/{identifier}/analyses").json() == before
    assert next(item for item in catalog if item["name"] == "regex_v1")["available"] is True


def test_facts_works_with_local_goal_run(tmp_path):
    root = Path(__file__).resolve().parents[2] / "commsfail/tests/fixtures"
    with TestClient(create_app(data_dir=tmp_path, source_root=root)) as client:
        response = client.post("/api/traces", json={"source": {"type": "local", "value": "goal_run"}})
        assert response.status_code == 200, response.text
        trace = response.json()
        assert isinstance(trace["conversation"]["description"], str)
        facts = next(item for item in trace["analyzers"] if item["name"] == "facts_v1")
        assert facts["available"] is True
        analysis = client.post(f"/api/traces/{trace['traceId']}/analyses/facts_v1", json={}).json()
        assert analysis["status"] == "completed", analysis
        assert analysis["output"]["output"]["applies"] is True
        assert analysis["output"]["output"]["findings"]


def wait_for_run(client, identifier):
    for _ in range(100):
        run = client.get(f"/api/analysis-runs/{identifier}").json()
        if run["status"] in ("completed", "failed"):
            return run
        time.sleep(0.01)
    raise AssertionError("Run did not finish.")


def test_async_scout_and_evidence_persistence(tmp_path, share):
    async def fake_scout(report, model, artifacts):
        assert report["messages"][0]["index"] == 1
        assert model == "mockllm/model"
        assert artifacts.exists()
        await asyncio.sleep(0.03)
        return {"findings": [{"category": "weak_handoff", "found": True, "message_numbers": [1]}]}

    with TestClient(create_app(data_dir=tmp_path, scout_runner=fake_scout)) as client:
        trace = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
        endpoint = f"/api/traces/{trace['traceId']}/analyses/scout_collaboration_v1"
        started = client.post(endpoint, json={"model": "mockllm/model"})
        assert started.status_code == 202
        duplicate = client.post(endpoint, json={"model": "mockllm/model"}).json()
        assert duplicate["id"] == started.json()["id"]
        completed = wait_for_run(client, started.json()["id"])
        assert completed["status"] == "completed"
        validate(completed, AnalysisRun.model_json_schema())
        assert completed["output"]["findings"][0]["message_numbers"] == [1]
        assert client.get(f"/api/traces/{trace['traceId']}").json()["analyses"]["scout_collaboration_v1"] == completed
    with TestClient(create_app(data_dir=tmp_path)) as client:
        assert client.get(f"/api/analysis-runs/{completed['id']}").json() == completed


def test_scout_errors_are_failures(tmp_path, share):
    async def failing_scout(*args):
        raise ValueError("Invalid model evidence")

    with TestClient(create_app(data_dir=tmp_path, scout_runner=failing_scout)) as client:
        trace = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
        started = client.post(f"/api/traces/{trace['traceId']}/analyses/scout_collaboration_v1", json={"model": "mockllm/model"}).json()
        failed = wait_for_run(client, started["id"])
        assert failed["status"] == "failed"
        assert failed["output"] is None
        assert "Invalid model evidence" in failed["error"]


def test_interrupted_runs_are_explicit_failures(tmp_path, share):
    with TestClient(create_app(data_dir=tmp_path)) as client:
        trace = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
    storage = Store(tmp_path)
    run = AnalysisRun(trace_id=trace["traceId"], analyzer={"name": "scout_collaboration_v1", "version": "2", "kind": "pipeline"})
    storage.save_run(run.record())
    with TestClient(create_app(data_dir=tmp_path)) as client:
        failed = client.get(f"/api/analysis-runs/{run.id}").json()
        assert failed["status"] == "failed"
        assert "API stopped" in failed["error"]
        assert failed["provenance"]["completed_at"]


def test_frontend_serving_is_confined(tmp_path):
    dist = tmp_path / "web"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>AgentTrace</h1>")
    (tmp_path / "secret.txt").write_text("outside")
    with TestClient(create_app(data_dir=tmp_path / "data", web_dist=dist)) as client:
        assert client.get("/").text == "<h1>AgentTrace</h1>"
        assert client.get("/api/missing").status_code == 404
        assert client.get("/missing.js").status_code == 404
        assert client.get("/%2e%2e%2fsecret.txt").status_code == 404
