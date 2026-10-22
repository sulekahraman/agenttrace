import asyncio
import copy
import json

import pytest
from commsfail import Trace
from commsfail.sources.sharednet import parse_turn
from fastapi.testclient import TestClient

from agenttrace.api import create_app
from agenttrace.communication import CLASSES, NAME, TAXONOMY_VERSION
from agenttrace.communication import analysis
from agenttrace.communication.analysis import Adjudication, Assessment, validate_assessment
from agenttrace.communication.evidence import (
    build_evidence, complete_window, digest, model_evidence, read_sequences,
    receipt_status, retrieve_evidence,
)
from agenttrace.store import Store
from test_api import wait_for_run


def synthetic_record(root):
    posts = [
        {"seq": 1, "who": "alpha", "text": "Use red.", "created_at": "2026-10-15T00:00:01Z", "role": "agent"},
        {"seq": 2, "who": "beta", "text": "I understood blue and used blue.", "created_at": "2026-10-15T00:00:03Z", "role": "agent"},
        {"seq": 3, "who": "alpha", "text": "Correction: use red.", "created_at": "2026-10-15T00:00:04Z", "role": "agent"},
        {"seq": 4, "who": "beta", "text": "Fixed: using red.", "created_at": "2026-10-15T00:00:06Z", "role": "agent"},
    ]
    ops, wakes = {}, []
    turns = [
        ("alpha", 1, [("sharednet say 'Use red.'", "posted", 1)]),
        ("beta", 1, [
            ("sharednet read --last 1", json.dumps({"items": [{"sequence": 1, "content": "Use red.\u2028Next."}]}, ensure_ascii=False), None),
            ("echo 'using blue'", "using blue", None),
            ("sharednet say 'I understood blue and used blue.'", "posted", 2),
        ]),
        ("alpha", 2, [("sharednet say 'Correction: use red.'", "posted", 3)]),
        ("beta", 2, [
            ("sharednet read --last 1", json.dumps({"items": [{"sequence": 3}]}), None),
            ("echo 'using red'", "using red", None),
            ("sharednet say 'Fixed: using red.'", "posted", 4),
        ]),
    ]
    for seat, turn, commands in turns:
        rows = []
        for i, (command, output, _) in enumerate(commands):
            item = {"id": f"item_{i}", "type": "command_execution", "command": command,
                    "aggregated_output": output, "exit_code": 0}
            rows.extend([{"type": "item.started", "item": item}, {"type": "item.completed", "item": item}])
        rows.append({"type": "turn.completed"})
        file = root / f"agents/{seat}/turn-{turn:03d}.jsonl"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows))
        parsed = parse_turn(file.read_text().split("\n"), "codex", turn)
        for op, (_, _, posted) in zip(parsed, commands):
            if posted:
                op["posted"] = posted
        ops.setdefault(seat, []).extend(parsed)
        wakes.append({"seat": seat, "turn": turn, "through": 0 if turn == 1 else 2,
                      "started_at": f"2026-10-15T00:00:0{2 if turn == 1 else 5}Z"})
    return Trace(room={"state": "closed", "name": "Synthetic communication"},
                 seats=[{"handle": "alpha"}, {"handle": "beta"}], posts=posts, ops=ops, wakes=wakes,
                 episode={"ended_by": {"trigger": "complete"}})


def assessment(failure=None):
    return {
        "explanation": "This assessment is limited to the evidence-supported opportunities in this fixture.",
        "incidents": [],
        "classes": [
            {"failure_class": key, "status": "supported_failure" if key == failure else "undecidable",
             "unknown_reasons": [] if key == failure else ["unclear_understanding"],
             "explanation": "Only the explicitly cited transition is assessable; other opportunities remain unknown."}
            for key in CLASSES
        ],
    }


def reading_assessment():
    value = assessment("reading")
    value["incidents"] = [{
        "id": "incident-1", "work_item": "Choose the agreed color", "actors": ["alpha", "beta"],
        "status": "supported", "failure_class": "reading", "anchor": "post:2",
        "information_post": "post:1", "dependent_event": "action:beta:1:1", "basis": "observed",
        "transitions": {
            "disclosure": {"status": "passed", "explanation": "The sender clearly requested red.",
                           "evidence": [{"event_id": "post:1", "quote": "Use red."}]},
            "delivery": {"status": "passed", "explanation": "The exact read returned the instruction before work.",
                         "evidence": [{"event_id": "action:beta:1:0", "quote": "sharednet read --last 1"}]},
            "reading": {"status": "failed", "explanation": "The recipient expressed blue instead of red and acted on it.",
                        "evidence": [{"event_id": "post:2", "quote": "I understood blue"},
                                     {"event_id": "action:beta:1:1", "quote": "using blue"}]},
            "action": {"status": "unknown", "explanation": "Not independently attributed after the earlier failure.", "evidence": []},
        },
        "consequence": "The demonstrated command used blue before correction.",
        "impact_status": "observed",
        "severity": 2, "severity_reason": "A command and correction exchange were repeated.",
        "recovery": {"status": "repaired", "explanation": "The later command and message show the correction.",
                     "evidence": [{"event_id": "action:beta:2:1", "quote": "using red"},
                                  {"event_id": "post:4", "quote": "Fixed: using red."}]},
    }]
    return value


def mock_communication_generation(monkeypatch, payload=None):
    pytest.importorskip("inspect_scout")
    from inspect_ai.model import ModelOutput
    from inspect_scout._llm_scanner import generate

    calls = []
    def install(payload):
        async def structured(input, schema, **kwargs):
            assert kwargs["model"] == "mockllm/model"
            assert kwargs["config"].cache is False
            assert schema.properties
            tag = input.split("Independent step: ")[1].split("\n")[0]
            calls.append(tag)
            if tag.startswith("search-"):
                data = {"explanation": "The initial index is sufficient for this synthetic reading fixture.", "windows": []}
                return data, [], ModelOutput.from_content("mockllm/model", json.dumps(data))
            data = copy.deepcopy(payload or assessment())
            if tag == "judge":
                data["decisions"] = [
                    {"candidate_id": f"{side}:{item['id']}", "decision": "kept",
                     "final_incident_id": item["id"], "reason": "The quoted evidence supports this merged incident."}
                    for side in ("A", "B") for item in data["incidents"]
                ]
            return data, [], ModelOutput.from_content("mockllm/model", json.dumps(data))
        monkeypatch.setattr(generate, "structured_generate", structured)
    install(payload)
    return calls


def test_exact_reads_unicode_and_prior_turn_receipt(tmp_path):
    trace = synthetic_record(tmp_path)
    bundle = build_evidence(trace, tmp_path)
    assert bundle["coverage"]["raw_turns"] == 4
    assert not bundle["coverage"]["missing_raw_turns"]
    assert receipt_status(bundle, "post:1", "action:beta:1:1") == "received"
    assert receipt_status(bundle, "post:1", "action:beta:2:1") == "received"
    assert receipt_status(bundle, "post:1", "action:beta:1:0") == "unknown"
    assert bundle["sha256"] == digest({key: val for key, val in bundle.items() if key != "sha256"})
    assert read_sequences('{"items":[{"sequence":7},{"sequence":9}]}') == [7, 9]
    assert read_sequences('{"items":[{"sequence":"7"}]}') is None


def test_bounded_read_and_unknown_wake_are_not_prefix_receipts(tmp_path):
    trace = synthetic_record(tmp_path)
    bundle = build_evidence(trace, tmp_path)
    action = next(event for event in bundle["events"] if event["id"] == "action:beta:1:1")
    action["receipt"]["known_received"] = [3]
    assert receipt_status(bundle, "post:1", action["id"]) == "not_received"
    action["receipt"]["initial_upper_bound"] = None
    assert receipt_status(bundle, "post:1", action["id"]) == "unknown"
    action["receipt"]["initial_upper_bound"] = 3
    assert receipt_status(bundle, "post:1", action["id"]) == "unknown"
    action["receipt"]["initial_upper_bound"] = 0
    action["timestamp"] = "2026-10-15T00:00:00Z"
    action["completed_at"] = "2026-10-15T00:00:08Z"
    assert receipt_status(bundle, "post:1", action["id"]) == "unknown"


def test_raw_source_is_explicit_frozen_and_validated(tmp_path):
    trace = synthetic_record(tmp_path)
    trace.source["path"] = str(tmp_path)
    assert not build_evidence(trace)["coverage"]["raw_outputs"]
    frozen = build_evidence(trace, tmp_path)
    file = tmp_path / "agents/beta/turn-001.jsonl"
    file.write_text(file.read_text().replace("using blue", "using gold"))
    assert frozen["sha256"] == digest({key: val for key, val in frozen.items() if key != "sha256"})
    with pytest.raises(ValueError, match="no longer matches"):
        build_evidence(trace, tmp_path)


def test_symlink_escape_is_rejected(tmp_path):
    trace = synthetic_record(tmp_path)
    outside = tmp_path / "other.jsonl"
    outside.write_text("{}")
    root = tmp_path / "record"
    (root / "agents/beta").mkdir(parents=True)
    (root / "agents/beta/turn-001.jsonl").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        build_evidence(trace, root)


def test_input_caps_are_explicit_and_prevent_absence_claims(tmp_path, monkeypatch):
    trace = synthetic_record(tmp_path)
    monkeypatch.setattr("agenttrace.communication.evidence.TEXT_LIMIT", 16)
    monkeypatch.setattr("agenttrace.communication.evidence.INPUT_LIMIT", 40)
    supplied = model_evidence(build_evidence(trace, tmp_path))
    assert supplied["coverage"]["truncated_events"]
    assert supplied["coverage"]["omitted_events"]
    assert sum(len(event["text"]) for event in supplied["events"]) <= 40
    assert supplied["events"][0]["kind"] == "post"


@pytest.mark.parametrize("failure", CLASSES)
def test_four_first_failure_contracts(tmp_path, failure):
    trace = synthetic_record(tmp_path)
    supplied = model_evidence(build_evidence(trace, tmp_path))
    value = reading_assessment()
    incident = value["incidents"][0]
    incident["failure_class"] = failure
    value["classes"] = assessment(failure)["classes"]
    for i, key in enumerate(CLASSES):
        incident["transitions"][key]["status"] = "passed" if i < CLASSES.index(failure) else "failed" if key == failure else "unknown"
        incident["transitions"][key]["evidence"] = [
            {"event_id": "post:1", "quote": "Use red."},
            {"event_id": "post:2", "quote": "I understood blue"},
            {"event_id": "action:beta:1:1", "quote": "using blue"},
        ]
    if failure == "delivery":
        dependent = next(event for event in supplied["events"] if event["id"] == incident["dependent_event"])
        dependent["receipt"]["known_received"] = []
    validate_assessment(Assessment.model_validate(value), supplied)


@pytest.mark.parametrize("mutation,match", [
    (lambda value: value["incidents"][0]["transitions"]["reading"]["evidence"][0].update(quote="invented"), "quotations"),
    (lambda value: value["incidents"][0]["transitions"]["delivery"].update(status="unknown"), "earlier transition"),
    (lambda value: value["incidents"][0].update(actors=["alpha", "alpha"]), "distinct"),
    (lambda value: value["incidents"][0].update(anchor="post:99"), "must exist"),
    (lambda value: value["classes"][2].update(status="no_failure_found"), "summaries"),
    (lambda value: value["incidents"][0]["recovery"].update(evidence=[]), "require quoted"),
    (lambda value: value["incidents"][0].update(dependent_event="action:alpha:1:0"), "quoted evidence"),
])
def test_invalid_attribution_is_rejected(tmp_path, mutation, match):
    supplied = model_evidence(build_evidence(synthetic_record(tmp_path), tmp_path))
    value = reading_assessment()
    mutation(value)
    with pytest.raises(ValueError, match=match):
        validate_assessment(Assessment.model_validate(value), supplied)


def test_unknown_and_recovery_remain_distinct(tmp_path):
    supplied = model_evidence(build_evidence(synthetic_record(tmp_path), tmp_path))
    value = reading_assessment()
    validate_assessment(Assessment.model_validate(value), supplied)
    incident = value["incidents"][0]
    incident.update(status="undecidable", failure_class=None)
    incident["transitions"]["delivery"]["status"] = "unknown"
    value["classes"] = assessment()["classes"]
    validate_assessment(Assessment.model_validate(value), supplied)


def test_future_acknowledgement_cannot_establish_prior_delivery(tmp_path):
    supplied = model_evidence(build_evidence(synthetic_record(tmp_path), tmp_path))
    value = reading_assessment()
    value["incidents"][0]["transitions"]["delivery"]["evidence"] = [
        {"event_id": "post:4", "quote": "Fixed: using red."},
    ]
    dependent = next(event for event in supplied["events"] if event["id"] == "action:beta:1:1")
    dependent["receipt"] = {}
    with pytest.raises(ValueError, match="receipt evidence"):
        validate_assessment(Assessment.model_validate(value), supplied)


def test_boundary_does_not_leak_episode_grade(tmp_path):
    trace = synthetic_record(tmp_path)
    trace.episode["grade"] = "external hidden verdict"
    boundary = next(event for event in build_evidence(trace)["events"] if event["kind"] == "boundary")
    assert "external hidden verdict" not in boundary["text"]


def test_overlapping_read_and_incomplete_logs_prevent_nonreceipt(tmp_path):
    trace = synthetic_record(tmp_path)
    file = tmp_path / "agents/beta/turn-001.jsonl"
    rows = [json.loads(line) for line in file.read_text().split("\n")]
    rows[0], rows[2] = rows[2], rows[0]
    rows[1], rows[3] = rows[3], rows[1]
    # The work begins before the overlapping read completes; it cannot establish a prior receipt.
    rows = [rows[0], rows[2], rows[3], rows[1], *rows[4:]]
    file.write_text("\n".join(json.dumps(row) for row in rows))
    trace.ops["beta"][:3] = parse_turn(file.read_text().split("\n"), "codex", 1)
    supplied = build_evidence(trace, tmp_path)
    action = next(event for event in supplied["events"] if event["id"] == "action:beta:1:1")
    assert not action["receipt"]["absence_checkable"]
    assert receipt_status(supplied, "post:1", action["id"]) == "unknown"
    file.write_text("\n".join(json.dumps(row) for row in rows if row["type"] != "turn.completed"))
    incomplete = build_evidence(trace, tmp_path)
    assert "beta:1" in incomplete["coverage"]["missing_raw_turns"]


@pytest.mark.parametrize("gap", ["raw_outputs", "run_closed", "truncated_events", "missing_raw_turns"])
def test_absence_requires_closed_complete_evidence(tmp_path, gap):
    supplied = model_evidence(build_evidence(synthetic_record(tmp_path), tmp_path))
    value = reading_assessment()
    value["incidents"][0]["basis"] = "absence"
    supplied["coverage"][gap] = False if gap in ("raw_outputs", "run_closed") else ["missing"]
    with pytest.raises(ValueError, match="complete supplied"):
        validate_assessment(Assessment.model_validate(value), supplied)


def test_real_structured_parser_independence_and_private_artifacts(tmp_path, monkeypatch):
    bundle = build_evidence(synthetic_record(tmp_path / "source"), tmp_path / "source")
    calls = mock_communication_generation(monkeypatch, reading_assessment())
    output = asyncio.run(analysis.analyze(bundle, "mockllm/model", tmp_path / "run"))
    assert calls == ["search-A", "search-B", "A", "B", "judge"]
    assert output["execution"]["generation_attempts"] == 5
    assert output["incidents"][0]["recovery"]["status"] == "repaired"
    assert output["classes"][2]["status"] == "supported_failure"
    assert output["taxonomy_version"] == TAXONOMY_VERSION
    assert output["evidence_sha256"] == bundle["sha256"]
    assert {item["candidate_id"] for item in output["decisions"]} == {"A:incident-1", "B:incident-1"}
    for file in (tmp_path / "run").iterdir():
        assert file.stat().st_mode & 0o077 == 0


def test_validation_retries_and_judge_accounting(tmp_path, monkeypatch):
    bundle = build_evidence(synthetic_record(tmp_path / "source"), tmp_path / "source")
    calls = []
    async def generate(prompt, schema, model):
        tag = prompt.split("Independent step: ")[1].split("\n")[0]
        calls.append(tag)
        if schema is analysis.EvidenceSearch:
            return schema.model_validate({"explanation": "Use the fixture's complete core events.", "windows": []})
        value = reading_assessment()
        if tag == "A" and calls.count("A") == 1:
            value["incidents"][0]["transitions"]["reading"]["evidence"][0]["quote"] = "invented"
        if schema is Adjudication:
            value["decisions"] = []
        return schema.model_validate(value)
    monkeypatch.setattr(analysis, "generate", generate)
    with pytest.raises(ValueError, match="judge exhausted.*every A/B"):
        asyncio.run(analysis.analyze(bundle, "mockllm/model", tmp_path / "run"))
    assert calls.count("A") == 2
    assert calls.count("B") == 1
    assert calls.count("judge") == 3
    assert (tmp_path / "run/A-1.errors.json").exists()


def test_unparsed_model_reply_retries_but_is_not_a_provider_exception(tmp_path, monkeypatch):
    import inspect_scout

    mock_communication_generation(monkeypatch, reading_assessment())
    original = inspect_scout.generate_answer
    rejected = False
    async def answer(prompt, *args, **kwargs):
        nonlocal rejected
        if "Independent step: search-A" in prompt and not rejected:
            rejected = True
            return None
        return await original(prompt, *args, **kwargs)
    monkeypatch.setattr(inspect_scout, "generate_answer", answer)
    bundle = build_evidence(synthetic_record(tmp_path / "source"), tmp_path / "source")
    output = asyncio.run(analysis.analyze(bundle, "mockllm/model", tmp_path / "run"))
    assert output["execution"]["generation_attempts"] == 6
    assert output["execution"]["calls"][0]["status"] == "validation_rejected"
    assert (tmp_path / "run/search-A-1.errors.json").exists()


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_provider_errors_are_explicit_and_cancel_sibling(tmp_path, monkeypatch, error_type):
    bundle = build_evidence(synthetic_record(tmp_path / "source"), tmp_path / "source")
    cancelled = []
    async def generate(prompt, schema, model):
        if "Independent step: search-A" in prompt:
            await asyncio.sleep(0.01)
            raise error_type("Provider unavailable")
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.append(True)
    monkeypatch.setattr(analysis, "generate", generate)
    with pytest.raises(error_type, match="Provider unavailable"):
        asyncio.run(analysis.analyze(bundle, "mockllm/model", tmp_path / "run"))
    assert cancelled == [True]
    execution = json.loads((tmp_path / "run/execution.json").read_text())
    assert execution["generation_attempts"] == 2
    assert all(call["status"] == "interrupted_or_provider_failure" for call in execution["calls"])


def test_solo_needs_no_provider_but_silent_second_agent_is_not_solo(tmp_path, monkeypatch):
    async def forbidden(*args):
        raise AssertionError("Unexpected provider call")
    monkeypatch.setattr(analysis, "generate", forbidden)
    trace = Trace(room={}, seats=[{"handle": "alpha"}], posts=[])
    output = asyncio.run(analysis.analyze(build_evidence(trace), "mockllm/model", tmp_path))
    assert all(item["status"] == "not_applicable" for item in output["classes"])
    assert json.loads((tmp_path / "execution.json").read_text()) == {"generation_attempts": 0, "calls": []}
    trace.seats.append({"handle": "beta"})
    assert len(build_evidence(trace)["coverage"]["agents"]) == 2


def test_api_setup_persistence_provenance_and_active_configuration(tmp_path, share, monkeypatch):
    calls = []
    async def runner(bundle, model, artifacts):
        calls.append(bundle)
        await asyncio.sleep(0.1)
        return {"schema": "test", "evidence_sha256": bundle["sha256"]}
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AGENTTRACE_COMMUNICATION_MODEL", "mockllm/model")
    data = tmp_path / "data"
    with TestClient(create_app(data_dir=data, communication_runner=runner)) as client:
        report = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
        identifier = report["traceId"]
        assert len([item for item in report["analyzers"] if item["name"] == NAME]) == 1
        assert not calls
        setup = client.get("/api/communication/setup", params={"trace_id": identifier}).json()
        assert setup["model"] == "mockllm/model"
        assert not setup["coverage"]["raw_outputs"]
        endpoint = f"/api/traces/{identifier}/analyses/{NAME}"
        created = client.post(endpoint, json={}).json()
        assert client.post(endpoint, json={}).json()["id"] == created["id"]
        assert client.post(endpoint, json={"model": "mockllm/other"}).status_code == 409
        completed = wait_for_run(client, created["id"])
        assert completed["status"] == "completed"
        assert completed["provenance"]["configuration_sha256"] == setup["configuration_sha256"]
        assert completed["provenance"]["evidence_sha256"] == calls[0]["sha256"]
        assert completed["provenance"]["taxonomy_version"] == TAXONOMY_VERSION
        assert client.get(f"/api/analysis-runs/{created['id']}/scout-view", follow_redirects=False).status_code == 409
    with TestClient(create_app(data_dir=data, communication_runner=runner)) as client:
        assert client.get(f"/api/traces/{identifier}").json()["analyses"][NAME] == completed
        assert Store(data).get_evidence(identifier)["sha256"] == calls[0]["sha256"]
        assert len(calls) == 1


def test_missing_key_blocks_only_explicit_communication_run(client, trace_response, monkeypatch):
    monkeypatch.setattr("agenttrace.api.importlib.util.find_spec", lambda _: object())
    monkeypatch.delenv("AGENTTRACE_COMMUNICATION_MODEL", raising=False)
    identifier = trace_response["traceId"]
    response = client.post(f"/api/traces/{identifier}/analyses/{NAME}", json={})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "communication_setup_required"
    assert len(client.get(f"/api/traces/{identifier}/analyses").json()) == 2
    assert client.get("/api/communication/setup?model=%20").status_code == 422


def test_communication_provider_failure_is_persisted(tmp_path, share):
    async def runner(bundle, model, artifacts):
        raise RuntimeError("Explicit communication provider failure")
    with TestClient(create_app(data_dir=tmp_path, communication_runner=runner)) as client:
        report = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}}).json()
        created = client.post(f"/api/traces/{report['traceId']}/analyses/{NAME}",
                              json={"model": "mockllm/model"}).json()
        failed = wait_for_run(client, created["id"])
        assert failed["status"] == "failed"
        assert failed["error"] == "Explicit communication provider failure"
        assert failed["provenance"]["evidence_sha256"]


def test_batch_opt_in_and_version_aware_reuse(tmp_path, share, monkeypatch):
    from agenttrace.batch import run_batch
    calls = []
    async def runner(bundle, model, artifacts):
        calls.append(model)
        return {"classes": []}
    options = {"model": "mockllm/model", "communication": True, "poll_interval": 0.01}
    with TestClient(create_app(data_dir=tmp_path / "data", communication_runner=runner)) as client:
        entries = [{"source": {"type": "share_json", "value": share}}]
        offline = run_batch(client, entries, tmp_path / "offline", "http://localhost:3000")
        assert not calls
        identifier = offline["traces"][0]["trace_id"]
        entries = [{"trace_id": identifier}]
        for folder in ("first", "cached"):
            result = run_batch(client, entries, tmp_path / folder, "http://localhost:3000", **options)
            assert result["traces"][0]["status"] == "completed"
        assert calls == ["mockllm/model"]
        monkeypatch.setattr("agenttrace.api.COMMUNICATION_PROMPT_VERSION", "future")
        result = run_batch(client, entries, tmp_path / "new-version", "http://localhost:3000", **options)
        assert result["traces"][0]["status"] == "completed"
        assert calls == ["mockllm/model", "mockllm/model"]


def detailed_bundle(tmp_path):
    bundle = build_evidence(synthetic_record(tmp_path), tmp_path)
    times = {
        ("alpha", 1): ["00"],
        ("alpha", 2): ["04"],
        ("beta", 1): ["02", "02.500", "03"],
        ("beta", 2): ["05", "05.500", "06"],
    }
    for event in bundle["events"]:
        if event["id"].startswith("action:"):
            event["timestamp"] = f"2026-10-15T00:00:{times[event['actor'], event['turn']][event['index']]}Z"
            event["completed_at"] = event["timestamp"]
    parent = next(e for e in bundle["events"] if e["id"] == "action:beta:1:1")
    detail_id = "detail:" + parent["id"]
    parent["text"] = json.dumps({**json.loads(parent["text"]), "full_detail_event": detail_id})
    bundle["events"].append({
        "id": detail_id, "parent": parent["id"], "kind": "detail", "actor": "beta",
        "timestamp": parent["timestamp"], "text": "x" * 9000 + "\nTARGETED_DIFF: used blue instead of red",
    })
    window = {"actors": ["alpha", "beta"], "start_event": "post:1", "end_event": "post:4"}
    return bundle, window


def test_discovery_details_are_balanced_across_agents():
    bundle = {
        "schema": "test", "sha256": "test", "coverage": {}, "events": [
            {"id": str(i), "kind": "detail", "actor": actor, "text": str(i)}
            for actor in ("alpha", "beta", "gamma") for i in range(3)
        ],
    }
    supplied = model_evidence(bundle)
    assert [e["actor"] for e in supplied["events"][:6]] == ["alpha", "beta", "gamma"] * 2


def test_full_window_restores_clipped_detail_and_scopes_absence(tmp_path):
    bundle, window = detailed_bundle(tmp_path)
    bundle["coverage"]["agents"].append("gamma")
    bundle["coverage"]["missing_raw_turns"] = ["gamma:1"]
    bundle["events"].append({
        "id": "detail:unrelated", "kind": "detail", "actor": "gamma",
        "timestamp": "2026-10-15T01:00:00Z", "text": "Unrelated omitted detail.",
    })
    discovery = model_evidence(bundle)
    assert "detail:action:beta:1:1" in discovery["coverage"]["truncated_events"]
    reviewed = retrieve_evidence(bundle, [window])
    assert "TARGETED_DIFF" in next(e["text"] for e in reviewed["events"] if e["id"] == "detail:action:beta:1:1")
    assert "detail:unrelated" in reviewed["coverage"]["omitted_events"]
    assert complete_window(reviewed, window)
    value = reading_assessment()
    value["incidents"][0].update(basis="absence", evidence_scope=window)
    validate_assessment(Assessment.model_validate(value), reviewed, require_reasons=True)
    reviewed["events"] = [e for e in reviewed["events"] if e["id"] != "detail:action:beta:1:1"]
    with pytest.raises(ValueError, match="complete retrieved"):
        validate_assessment(Assessment.model_validate(value), reviewed, require_reasons=True)


@pytest.mark.parametrize("gap", ["missing_raw_turns", "incomplete_tool_calls", "capture_compactions"])
def test_relevant_source_gap_blocks_scoped_absence(tmp_path, gap):
    bundle, window = detailed_bundle(tmp_path)
    bundle["coverage"][gap] = ["beta:1"]
    assert not complete_window(retrieve_evidence(bundle, [window]), window)


def test_retrieval_includes_actions_overlapping_window_start(tmp_path):
    bundle, window = detailed_bundle(tmp_path)
    action = next(e for e in bundle["events"] if e["id"] == "action:beta:1:1")
    detail = next(e for e in bundle["events"] if e.get("parent") == action["id"])
    action["timestamp"] = detail["timestamp"] = "2026-10-15T00:00:00Z"
    reviewed = retrieve_evidence(bundle, [window])
    assert "TARGETED_DIFF" in next(e["text"] for e in reviewed["events"] if e["id"] == detail["id"])


def test_retrieval_over_budget_fails_explicitly(tmp_path, monkeypatch):
    bundle, window = detailed_bundle(tmp_path)
    monkeypatch.setattr("agenttrace.communication.evidence.REVIEW_TEXT_LIMIT", 100)
    with pytest.raises(ValueError, match="narrower windows"):
        retrieve_evidence(bundle, [window])


def test_missing_later_turn_does_not_invalidate_earlier_complete_window(tmp_path):
    bundle, window = detailed_bundle(tmp_path)
    bundle["coverage"]["missing_raw_turns"] = ["beta:2"]
    window["end_event"] = "post:2"
    assert complete_window(retrieve_evidence(bundle, [window]), window)


@pytest.mark.parametrize("field,value", [
    ("timestamp", "2026-10-15T00:00:02"),
    ("completed_at", "2026-10-15T00:00:02"),
    ("completed_at", None),
    ("completed_at", "2026-10-15T00:00:01Z"),
])
def test_untimed_action_blocks_absence_without_crashing(tmp_path, field, value):
    bundle, window = detailed_bundle(tmp_path)
    next(e for e in bundle["events"] if e["id"] == "action:beta:1:1")[field] = value
    reviewed = retrieve_evidence(bundle, [window])
    assert not complete_window(reviewed, window)
    assert "untimed_actions" in reviewed["coverage"]["retrieval_windows"][0]["source_gaps"]


def test_parent_link_restores_untimed_details_and_missing_detail_blocks_completeness(tmp_path):
    bundle, window = detailed_bundle(tmp_path)
    detail = next(e for e in bundle["events"] if e.get("parent") == "action:beta:1:1")
    detail["timestamp"] = None
    reviewed = retrieve_evidence(bundle, [window])
    assert complete_window(reviewed, window)
    assert detail["id"] in {e["id"] for e in reviewed["events"]}
    bundle["events"].remove(detail)
    reviewed = retrieve_evidence(bundle, [window])
    assert not complete_window(reviewed, window)
    assert "missing_full_details" in reviewed["coverage"]["retrieval_windows"][0]["source_gaps"]


def test_observed_disclosure_does_not_require_recipient_reliance_or_harm(tmp_path):
    bundle, window = detailed_bundle(tmp_path)
    value = reading_assessment()
    value["classes"] = assessment("disclosure")["classes"]
    incident = value["incidents"][0]
    incident.update(failure_class="disclosure", dependent_event=None, impact_status="not_established",
                    severity=None, consequence="The inaccurate message is observable; recipient reliance and harm are not established.")
    incident["transitions"]["disclosure"].update(
        status="failed", explanation="The shared account contradicts the available instruction.",
        evidence=[{"event_id": "post:2", "quote": "I understood blue"}],
    )
    validate_assessment(Assessment.model_validate(value), retrieve_evidence(bundle, [window]), require_reasons=True)
    incident["severity"] = 4
    with pytest.raises(ValueError, match="invented cost"):
        validate_assessment(Assessment.model_validate(value), retrieve_evidence(bundle, [window]), require_reasons=True)


def test_unknown_reasons_and_negative_search_scope_are_required(tmp_path):
    bundle, window = detailed_bundle(tmp_path)
    reviewed = retrieve_evidence(bundle, [window])
    value = assessment()
    value["classes"][0]["unknown_reasons"] = []
    with pytest.raises(ValueError, match="unknown_reasons"):
        validate_assessment(Assessment.model_validate(value), reviewed, require_reasons=True)
    value["classes"][0].update(status="no_failure_found")
    with pytest.raises(ValueError, match="complete reviewed"):
        validate_assessment(Assessment.model_validate(value), reviewed, require_reasons=True)
    value["classes"][0]["evidence_scope"] = [window]
    validate_assessment(Assessment.model_validate(value), reviewed, require_reasons=True)


def test_independent_search_review_and_union_judge_restore_full_details(tmp_path, monkeypatch):
    bundle, window = detailed_bundle(tmp_path / "source")
    prompts = {}
    async def generated(prompt, schema, model):
        tag = prompt.split("Independent step: ")[1].split("\n")[0]
        prompts[tag] = prompt
        if schema is analysis.EvidenceSearch:
            return schema.model_validate({"explanation": "Inspect the complete color-change window.", "windows": [window]})
        value = reading_assessment()
        value["incidents"][0]["transitions"]["reading"]["evidence"].append({
            "event_id": "detail:action:beta:1:1", "quote": "TARGETED_DIFF",
        })
        if schema is Adjudication:
            value["decisions"] = [
                {"candidate_id": f"{role}:incident-1", "decision": "kept", "final_incident_id": "incident-1",
                 "reason": "The restored full edit supports the merged breakdown."} for role in ("A", "B")
            ]
        return schema.model_validate(value)
    monkeypatch.setattr(analysis, "generate", generated)
    output = asyncio.run(analysis.analyze(bundle, "mockllm/model", tmp_path / "run"))
    assert list(prompts) == ["search-A", "search-B", "A", "B", "judge"]
    assert all("TARGETED_DIFF" not in prompts[tag] for tag in ("search-A", "search-B"))
    assert all("TARGETED_DIFF" in prompts[tag] for tag in ("A", "B", "judge"))
    assert "A:incident-1" not in prompts["B"]
    assert output["execution"]["generation_attempts"] == 5
    assert complete_window({"events": output["evidence"], "coverage": output["coverage"]}, window)
    assert (tmp_path / "run/A-review-evidence.json").exists()
    assert (tmp_path / "run/search-A-1.prompt.json").exists()
    assert json.loads((tmp_path / "run/judge-1.prompt.json").read_text())["response_schema"]


def test_all_five_stages_can_each_use_three_validation_attempts(tmp_path, monkeypatch):
    bundle, window = detailed_bundle(tmp_path / "source")
    counts = {}
    async def generated(prompt, schema, model):
        tag = prompt.split("Independent step: ")[1].split("\n")[0]
        counts[tag] = counts.get(tag, 0) + 1
        if schema is analysis.EvidenceSearch:
            scope = window if counts[tag] == 3 else {**window, "end_event": "invented"}
            return schema.model_validate({"explanation": "Review the full color-change interval.", "windows": [scope]})
        value = reading_assessment()
        if counts[tag] < 3:
            value["incidents"][0]["transitions"]["reading"]["evidence"][0]["quote"] = "invented"
        if schema is Adjudication:
            value["decisions"] = [
                {"candidate_id": f"{role}:incident-1", "decision": "kept", "final_incident_id": "incident-1",
                 "reason": "The full evidence supports the merged candidate."} for role in ("A", "B")
            ]
        return schema.model_validate(value)
    monkeypatch.setattr(analysis, "generate", generated)
    output = asyncio.run(analysis.analyze(bundle, "mockllm/model", tmp_path / "run"))
    assert counts == {tag: 3 for tag in ("search-A", "search-B", "A", "B", "judge")}
    assert output["execution"]["generation_attempts"] == 15
    assert sum(call["status"] == "validation_rejected" for call in output["execution"]["calls"]) == 10
    assert "VALIDATION FEEDBACK" in json.loads((tmp_path / "run/search-A-3.prompt.json").read_text())["prompt"]
