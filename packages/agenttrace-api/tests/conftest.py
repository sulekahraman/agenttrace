import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agenttrace.api import create_app

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


@pytest.fixture
def share():
    return json.loads((FIXTURES / "ui-share.json").read_text())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTTRACE_SCOUT_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(create_app(data_dir=tmp_path / "data")) as client:
        yield client


@pytest.fixture
def trace_response(client, share):
    response = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}})
    assert response.status_code == 200, response.text
    return response.json()
