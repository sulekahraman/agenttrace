import httpx
import pytest

from agenttrace.sources import Source, load_source, validate_share_url


@pytest.mark.parametrize("value", [
    "http://www.sharednet.ai/s/shr_example",
    "https://evil.test/s/shr_example",
    "https://www.sharednet.ai:443/s/shr_example",
    "https://user@sharednet.ai/s/shr_example",
    "https://sharednet.ai/s/shr_example?redirect=evil",
    "https://sharednet.ai/profile",
])
def test_rejects_non_share_urls(value):
    with pytest.raises(ValueError):
        validate_share_url(value)


def test_accepts_public_share_link():
    assert validate_share_url("https://www.sharednet.ai/s/shr_example/") == "shr_example"


def test_local_sources_are_allowlisted(tmp_path):
    with pytest.raises(ValueError, match="disabled"):
        load_source(Source(type="local", value="share.json"))
    with pytest.raises(ValueError, match="inside"):
        load_source(Source(type="local", value="../outside.json"), tmp_path)
    with pytest.raises(ValueError, match="symlink|inside"):
        (tmp_path / "escape").symlink_to(tmp_path.parent)
        load_source(Source(type="local", value="escape"), tmp_path)


def test_uses_bounded_fixed_host_fetch(monkeypatch, share):
    real_client = httpx.Client
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=share)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(handle)
    ))
    trace = load_source(Source(type="sharednet_share", value="https://www.sharednet.ai/s/shr_example"))
    assert requests[0].url.host == "www.sharednet.ai"
    assert requests[0].url.path == "/api/sharednet/shared/shr_example"
    assert len(trace.posts) == 3


def test_does_not_follow_share_redirect(monkeypatch):
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "http://localhost/"}))
    ))
    with pytest.raises(ValueError, match="302"):
        load_source(Source(type="sharednet_share", value="https://www.sharednet.ai/s/shr_example"))


def test_malformed_share_is_rejected(client):
    result = client.post("/api/traces", json={"source": {"type": "share_json", "value": {"messages": [{"sequence": "wrong"}]}}})
    assert result.status_code == 400


@pytest.mark.parametrize("field,value", [
    ("created_at", 123), ("sender", {"handle": []}), ("content", []),
])
def test_malformed_message_fields_are_client_errors(client, share, field, value):
    share["messages"][0][field] = value
    response = client.post("/api/traces", json={"source": {"type": "share_json", "value": share}})
    assert response.status_code == 400
