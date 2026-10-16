import asyncio
import base64
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest

pytest.importorskip("inspect_scout")

from inspect_scout import scan_results_df, transcripts_db

from agenttrace.api import scout_viewer_base_url
from agenttrace.models import AnalysisRun, Analyzer, Provenance
from agenttrace.scout.adapter import transcript_from_report
from agenttrace.scout import viewer


@pytest.fixture
def saved_run(trace_response):
    return AnalysisRun(
        trace_id=trace_response["traceId"],
        analyzer=Analyzer(name="scout_collaboration_v1", version="2.1.0", kind="pipeline"),
        provenance=Provenance(model="openai/original-model", prompt_version="3"),
        status="completed",
        output={
            "annotations": [
                {
                    "message_number": message["index"],
                    "primary_type": "status_update" if position == 2 else "social_heartbeat",
                    "confidence": 0.9, "ambiguous": False, "rationale": "Saved annotation.",
                }
                for position, message in enumerate(trace_response["messages"])
            ],
            "findings": [
                {
                    "category": category,
                    "found": category == "weak_handoff",
                    "explanation": "Saved finding cites [M2].",
                    "confidence": 0.8,
                    "message_numbers": [3] if category == "weak_handoff" else [],
                }
                for category in ["duplicated_work", "weak_handoff", "unintegrated_information"]
            ],
        },
    ).record()


def test_native_export_is_faithful_cached_and_never_generates(tmp_path, trace_response, saved_run, monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Saved-result exports must not call a model.")

    monkeypatch.setattr("inspect_ai.model.Model.generate", forbidden)
    root = tmp_path / "viewer"
    exported = viewer.export_saved_run(trace_response, saved_run, root)
    native = scan_results_df(exported["location"])
    assert native.complete and not native.errors
    assert native.spec.metadata["original_provenance"] == saved_run["provenance"]
    assert native.spec.metadata["agenttrace_run_id"] == saved_run["id"]
    assert native.spec.metadata["generation_logs_available"] is False
    for scanner in native.spec.scanners.values():
        assert set(scanner.params) == {"results_file"}
    for name, frame in native.scanners.items():
        assert len(frame) == 3
        assert set(frame.transcript_id) == {saved_run["trace_id"]}
        assert (frame.scan_total_tokens.fillna(0) == 0).all()
        if name == "saved_message_annotations":
            assert list(frame.value) == ["social_heartbeat", "social_heartbeat", "status_update"]
            assert list(frame.explanation) == ["Saved annotation."] * 3
        else:
            assert list(frame.value) == [False, True, False]
            assert list(frame.explanation) == ["Saved finding cites [M2]."] * 3
    with monkeypatch.context() as patch:
        patch.setattr(viewer, "scan", lambda **kwargs: pytest.fail("Cached exports must not scan again."))
        assert viewer.export_saved_run(trace_response, saved_run, root) == exported
    second = deepcopy(saved_run)
    second["id"] = f"run_{uuid4().hex}"
    second_export = viewer.export_saved_run(trace_response, second, root)
    assert second_export["location"] != exported["location"]

    async def count():
        async with transcripts_db(str(root / "transcripts")) as database:
            return await database.count()

    assert asyncio.run(count()) == 1
    assert root.stat().st_mode & 0o777 == 0o700
    other_report = deepcopy(trace_response)
    other_report["traceId"] = "trace_other"
    other_run = {**saved_run, "id": f"run_{uuid4().hex}", "trace_id": "trace_other"}
    other_export = viewer.export_saved_run(other_report, other_run, root)
    for frame in scan_results_df(other_export["location"]).scanners.values():
        assert len(frame) == 3
        assert set(frame.transcript_id) == {"trace_other"}
    assert asyncio.run(count()) == 2


def test_candidate_citations_map_to_original_message_ids(trace_response, saved_run):
    transcript = transcript_from_report(trace_response)
    annotations, findings = viewer.saved_results(transcript, saved_run["output"])
    assert annotations[2].references[0].id == transcript.messages[2].id
    assert findings[1].references[0].id == transcript.messages[2].id
    assert findings[1].references[0].cite == "M2"


def test_export_rejects_wrong_trace_and_incomplete_annotations(tmp_path, trace_response, saved_run):
    wrong = {**saved_run, "trace_id": "different"}
    with pytest.raises(ValueError, match="does not belong"):
        viewer.export_saved_run(trace_response, wrong, tmp_path)
    saved_run["output"]["annotations"].pop()
    with pytest.raises(ValueError, match="exactly once"):
        viewer.export_saved_run(trace_response, saved_run, tmp_path)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:7576", "http://example.org:7576",
    "http://user:password@localhost:7576", "http://localhost:7576/path",
    "http://localhost:7576?query=1", "http://localhost:7576/#fragment",
    "http://localhost:0", "http://localhost:not-a-port",
])
def test_viewer_origin_is_loopback_only(monkeypatch, url):
    monkeypatch.setenv("AGENTTRACE_SCOUT_VIEWER_URL", url)
    with pytest.raises(ValueError):
        scout_viewer_base_url()


def mock_viewer(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        "agenttrace.api.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_api_redirects_exact_saved_run_without_reanalysis(client, trace_response, saved_run, monkeypatch, tmp_path):
    client.app.state.store.save_run(saved_run)
    root = tmp_path / "data" / "scout-view"
    mock_viewer(monkeypatch, lambda request: httpx.Response(200, json={
        name: {"dir": (root / name).resolve().as_uri()} for name in ["scans", "transcripts"]
    }))
    location = root / "scans" / "scan_id=test"
    calls = []

    def export(report, run, directory):
        calls.append((report["traceId"], run["id"], directory))
        return {"location": str(location)}

    monkeypatch.setattr(viewer, "export_saved_run", export)
    response = client.get(f"/api/analysis-runs/{saved_run['id']}/scout-view", follow_redirects=False)
    assert response.status_code == 303
    encoded = base64.urlsafe_b64encode(location.parent.resolve().as_uri().encode()).decode().rstrip("=")
    assert response.headers["location"] == f"http://127.0.0.1:7576/#/scan/{encoded}/scan_id=test"
    assert calls == [(trace_response["traceId"], saved_run["id"], root.resolve())]
    assert client.app.state.store.get_run(saved_run["id"]) == saved_run


def test_api_rejects_ineligible_runs_and_missing_dependencies(client, trace_response, saved_run, monkeypatch):
    assert client.get("/api/analysis-runs/missing/scout-view").status_code == 404
    offline = next(iter(trace_response["analyses"].values()))
    assert client.get(f"/api/analysis-runs/{offline['id']}/scout-view").status_code == 409
    for status in ["queued", "running", "failed"]:
        client.app.state.store.save_run({**saved_run, "status": status})
        assert client.get(f"/api/analysis-runs/{saved_run['id']}/scout-view").status_code == 409
    client.app.state.store.save_run(saved_run)
    monkeypatch.setattr("agenttrace.api.importlib.util.find_spec", lambda name: None)
    assert client.get(f"/api/analysis-runs/{saved_run['id']}/scout-view").status_code == 503


@pytest.mark.parametrize("config", [{}, {"scans": None}, None])
def test_api_reports_wrong_viewer_configuration(client, saved_run, monkeypatch, config):
    client.app.state.store.save_run(saved_run)
    mock_viewer(monkeypatch, lambda request: httpx.Response(200, json=config))
    monkeypatch.setattr(viewer, "export_saved_run", lambda *args: pytest.fail("Do not export to the wrong viewer."))
    assert client.get(f"/api/analysis-runs/{saved_run['id']}/scout-view").status_code == 503


def test_api_reports_stopped_viewer(client, saved_run, monkeypatch):
    client.app.state.store.save_run(saved_run)

    def unavailable(request):
        raise httpx.ConnectError("Viewer stopped.", request=request)

    mock_viewer(monkeypatch, unavailable)
    response = client.get(f"/api/analysis-runs/{saved_run['id']}/scout-view")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_api_surfaces_export_failure(client, saved_run, monkeypatch, tmp_path, caplog):
    client.app.state.store.save_run(saved_run)
    root = tmp_path / "data" / "scout-view"
    mock_viewer(monkeypatch, lambda request: httpx.Response(200, json={
        name: {"dir": (root / name).as_uri()} for name in ["scans", "transcripts"]
    }))

    def failed(*args):
        raise RuntimeError("Native recording failed.")

    monkeypatch.setattr(viewer, "export_saved_run", failed)
    response = client.get(f"/api/analysis-runs/{saved_run['id']}/scout-view")
    assert response.status_code == 500
    assert "export failed" in response.json()["detail"]
    assert "Native recording failed" in caplog.text
    assert client.app.state.store.get_run(saved_run["id"]) == saved_run
