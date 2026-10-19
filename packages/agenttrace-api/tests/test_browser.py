"""Opt-in browser test against a real API and Scout's structured parser, without model charges."""
import os
import socket
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("AGENTTRACE_BROWSER_TESTS") != "1",
    reason="Set AGENTTRACE_BROWSER_TESTS=1 and install the browser extra and Chromium.",
)


def test_ui_ingestion_scout_evidence_and_reload(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright
    import uvicorn
    from agenttrace.api import create_app
    from test_scout_pipeline import mock_structured_generation

    mock_structured_generation(monkeypatch)
    monkeypatch.delenv("AGENTTRACE_SCOUT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    root = Path(__file__).resolve().parents[3]
    assert (root / "apps/web/dist/index.html").exists(), "Run npm run build first."
    server = uvicorn.Server(uvicorn.Config(
        create_app(data_dir=tmp_path / "data", source_root=root / "packages/commsfail/tests/fixtures"),
        log_level="error",
    ))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.02)
            assert server.started
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{port}")
                    page.get_by_role("heading", name="AgentTrace", exact=True).wait_for()
                    page.get_by_label("Trace source").select_option("share_json")
                    page.get_by_label("Share JSON file", exact=True).set_input_files(root / "fixtures/ui-share.json")
                    page.get_by_role("button", name="Analyze", exact=True).click()
                    page.get_by_role("heading", name="Test room", exact=True).wait_for()
                    expect(page.get_by_role("button", name="Select Claims vs. actions", exact=True)).to_be_disabled()
                    expect(page.get_by_role("button", name="Select Conversation patterns", exact=True)).to_be_enabled()
                    expect(page.get_by_role("group", name="Offline annotators").get_by_role("button").first).to_have_attribute("aria-label", "Select Conversation patterns")
                    expect(page.get_by_role("button", name="Select Conversation patterns", exact=True)).to_have_attribute("aria-pressed", "true")
                    page.get_by_text("Requires per-agent execution logs from a local goal-run record", exact=False).wait_for()
                    expect(page.get_by_label("Model", exact=True)).to_have_value("openai/gpt-5.4-mini")
                    with page.expect_response(lambda response: response.url.endswith("/analyses/scout_collaboration_v1")) as response:
                        page.get_by_role("button", name="Run Scout", exact=True).click()
                    setup_error = response.value.json()["detail"]
                    assert setup_error["code"] == "scout_setup_required"
                    dialog = page.get_by_role("dialog")
                    expect(dialog).to_be_visible()
                    expect(dialog).to_contain_text('read -s "OPENAI_API_KEY?Paste your OpenAI API key: "; echo')
                    expect(dialog).to_contain_text("export OPENAI_API_KEY")
                    expect(dialog).not_to_contain_text('export OPENAI_API_KEY="your-api-key"')
                    expect(dialog).to_contain_text("Stop AgentTrace, then run")
                    expect(dialog).not_to_contain_text("macOS/zsh")
                    expect(dialog).to_contain_text("activate the Python environment where AgentTrace is installed")
                    expect(dialog.locator("ol pre code")).to_have_text('read -s "OPENAI_API_KEY?Paste your OpenAI API key: "; echo\nexport OPENAI_API_KEY\nagenttrace')
                    expect(dialog.locator("ol > li")).to_have_count(3)
                    assert len(dialog.inner_text().split()) <= 120
                    expect(dialog.locator("details")).not_to_have_attribute("open", "")
                    dialog.get_by_text("Other shells & details", exact=True).click()
                    expect(dialog).to_contain_text("A ChatGPT subscription does not include API usage")
                    expect(dialog).to_contain_text('read -r -s -p "Paste your OpenAI API key: " OPENAI_API_KEY; echo')
                    expect(dialog.get_by_role("link", name="OpenAI API dashboard")).to_have_attribute("href", "https://platform.openai.com/api-keys")
                    identifier = page.url.split("?trace=")[1]
                    runs = page.request.get(f"http://127.0.0.1:{port}/api/traces/{identifier}/analyses").json()
                    assert len(runs) == 2
                    dialog.get_by_role("button", name="Close", exact=True).click()
                    expect(dialog).not_to_be_visible()
                    page.get_by_role("button", name="Provider setup", exact=True).click()
                    expect(dialog).to_be_visible()
                    page.keyboard.press("Escape")
                    expect(dialog).not_to_be_visible()
                    assert page.locator("tbody tr").count() == 3
                    assert page.locator(".plot-container").count() == 3
                    for chart in page.locator(".plot-container").all():
                        assert chart.locator("svg").count() >= 1
                    page.locator(".plot-container").nth(0).locator("g[aria-label='bar'] rect").first.click()
                    expect(page.locator("tbody tr")).to_have_count(1)
                    page.get_by_role("button", name="Reset filters", exact=True).click()
                    page.locator(".plot-container").nth(1).locator("g[aria-label='bar'] rect").first.click()
                    expect(page.locator("tbody tr")).to_have_count(2)
                    page.get_by_role("button", name="Reset filters", exact=True).click()
                    page.locator(".plot-container").nth(2).locator("g[aria-label='cell'] rect").first.click(position={"x": 8, "y": 8})
                    expect(page.locator("tbody tr")).to_have_count(1)
                    page.locator(".plot-container").nth(2).locator("g[aria-label='text'] text").first.click()
                    expect(page.locator("tbody tr")).to_have_count(3)
                    page.get_by_label("Search", exact=True).fill("verify")
                    assert page.locator("tbody tr").count() == 1
                    page.get_by_role("button", name="Reset filters", exact=True).click()
                    assert page.locator("tbody tr").count() == 3
                    page.get_by_role("heading", name="Communication failures", exact=True).wait_for()
                    with page.expect_response(lambda response: response.url.endswith("/analyses/regex_v1")) as response:
                        page.get_by_role("button", name="Run annotator", exact=True).click()
                    assert response.value.json()["status"] == "completed"
                    page.get_by_label("Model", exact=True).fill("mockllm/model")
                    page.get_by_role("button", name="Run Scout", exact=True).click()
                    page.get_by_role("heading", name="weak handoff", exact=True).wait_for(timeout=15000)
                    page.get_by_role("button", name="Message #1", exact=True).last.click()
                    assert page.locator("tbody tr").count() == 1
                    assert "Could you verify" in page.locator("tbody tr").inner_text()
                    page.reload()
                    page.get_by_role("heading", name="weak handoff", exact=True).wait_for()
                    expect(page.get_by_label("Model", exact=True)).to_have_value("mockllm/model")
                    assert page.locator("tbody tr").count() == 3
                    with page.expect_download() as download:
                        page.get_by_role("button", name="Export for Scout", exact=True).click()
                    assert download.value.suggested_filename == "agenttrace-scout-transcript.json"
                    page.route("**/api/traces/*/analyses/scout_collaboration_v1", lambda route: route.fulfill(
                        status=422, json={"detail": "Mock model error"}
                    ))
                    page.get_by_role("button", name="Run Scout", exact=True).click()
                    page.get_by_role("alert").filter(has_text="Mock model error").wait_for()
                    page.get_by_label("Trace source").select_option("local")
                    page.get_by_label("Path relative to configured data directory", exact=True).fill("goal_run")
                    page.get_by_role("button", name="Analyze", exact=True).click()
                    page.get_by_role("heading", name="goal_run", exact=True).wait_for()
                    expect(page.get_by_role("button", name="Select Claims vs. actions", exact=True)).to_be_enabled()
                    page.get_by_role("button", name="Select Claims vs. actions", exact=True).click()
                    expect(page.get_by_role("button", name="Select Claims vs. actions", exact=True)).to_have_attribute("aria-pressed", "true")
                    with page.expect_response(lambda response: response.url.endswith("/analyses/facts_v1")) as response:
                        page.get_by_role("button", name="Run annotator", exact=True).click()
                    analysis = response.value.json()
                    assert analysis["status"] == "completed"
                    finding = analysis["output"]["output"]["findings"][0]
                    page.get_by_role("heading", name=finding["fact"].replace("_", " "), exact=True).first.wait_for()
                    page.get_by_role("button", name=f"Message #{finding['seq']}", exact=True).first.click()
                    expect(page.locator("tbody tr")).to_have_count(1)
                    page.get_by_label("Trace source").select_option("share_json")
                    page.get_by_label("Share JSON file", exact=True).set_input_files(root / "fixtures/ui-share.json")
                    page.get_by_role("button", name="Analyze", exact=True).click()
                    page.get_by_role("heading", name="Test room", exact=True).wait_for()
                    expect(page.get_by_role("button", name="Select Conversation patterns", exact=True)).to_have_attribute("aria-pressed", "true")
                    expect(page.get_by_role("button", name="Select Claims vs. actions", exact=True)).to_be_disabled()
                    assert not errors, errors
                finally:
                    browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()


def test_communication_setup_incident_action_evidence_and_replay(tmp_path, monkeypatch):
    from playwright.sync_api import expect, sync_playwright
    import uvicorn
    from agenttrace.api import create_app
    from agenttrace.communication import NAME
    from agenttrace.communication.evidence import build_evidence
    from agenttrace.store import Store
    from agenttrace.view_model import trace_id
    from test_communication import mock_communication_generation, reading_assessment, synthetic_record

    trace = synthetic_record(tmp_path / "source")
    data = tmp_path / "data"
    store = Store(data)
    identifier = trace_id(trace)
    store.save_trace(identifier, trace)
    store.save_evidence(identifier, build_evidence(trace, tmp_path / "source"))
    calls = mock_communication_generation(monkeypatch, reading_assessment())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENTTRACE_COMMUNICATION_MODEL", raising=False)
    server = uvicorn.Server(uvicorn.Config(create_app(data_dir=data), log_level="error"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]})
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.02)
            assert server.started
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(f"http://127.0.0.1:{listener.getsockname()[1]}/?trace={identifier}")
                    panel = page.get_by_role("region", name="Communication failure analysis setup")
                    expect(panel.get_by_label("Communication model", exact=True)).to_have_value("openai/gpt-5.4-mini")
                    panel.get_by_role("button", name="Communication provider setup", exact=True).click()
                    expect(panel.get_by_role("alert")).to_contain_text("OPENAI_API_KEY")
                    assert not calls
                    panel.get_by_label("Communication model", exact=True).fill("mockllm/model")
                    panel.get_by_role("button", name="Run communication analysis", exact=True).click()
                    panel.get_by_role("heading", name="incident-1: reading", exact=False).wait_for(timeout=15000)
                    expect(panel).to_contain_text("Recovery: repaired")
                    panel.get_by_text("reading: failed", exact=True).click()
                    panel.get_by_role("button", name="Message #2", exact=True).click()
                    expect(page.locator("tbody tr")).to_have_count(1)
                    expect(page.locator("tbody tr")).to_contain_text("I understood blue")
                    panel.get_by_text("action:beta:1:1", exact=True).click()
                    expect(panel.locator("pre").filter(has_text="echo 'using blue'").first).to_be_visible()
                    assert calls == ["A", "B", "judge"]
                    page.reload()
                    panel.get_by_role("heading", name="incident-1: reading", exact=False).wait_for()
                    expect(panel.get_by_label("Communication model", exact=True)).to_have_value("mockllm/model")
                    assert calls == ["A", "B", "judge"]
                    saved = page.request.get(f"http://127.0.0.1:{listener.getsockname()[1]}/api/traces/{identifier}/analyses").json()
                    assert len([run for run in saved if run["analyzer"]["name"] == NAME]) == 1
                    assert not errors, errors
                finally:
                    browser.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
