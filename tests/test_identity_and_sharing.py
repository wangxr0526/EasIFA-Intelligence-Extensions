from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import stat

import httpx
import pytest

from easifa_mcp.client import EasifaAgentClient
from easifa_mcp.config import EasifaMCPSettings
from easifa_mcp.identity import load_owner_key


def settings(**kwargs):
    return EasifaMCPSettings(
        agent_base_url="https://gateway.example/easifa-agent",
        backend_base_url="https://backend.example/easifa",
        public_web_base_url="https://web.example/easifa",
        **kwargs,
    )


def test_identity_persists_in_browser_recovery_format():
    config = settings()
    key = load_owner_key(config)
    assert len(key) == 43
    assert load_owner_key(config) == key
    assert json.loads(config.owner_file().read_text()) == {
        "format": "easifa-access", "version": 1, "token": key,
    }
    if os.name == "posix":
        assert stat.S_IMODE(config.owner_file().stat().st_mode) == 0o600


def test_concurrent_startups_keep_one_identity():
    config = settings()
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: load_owner_key(config), range(24)))
    assert len(set(keys)) == 1
    assert load_owner_key(config) == keys[0]
    assert list(config.owner_file().parent.iterdir()) == [config.owner_file()]


def test_explicit_key_takes_priority_and_is_not_in_settings_repr(tmp_path, monkeypatch):
    path = tmp_path / "broken.json"
    path.write_text("keep this existing file")
    key = secrets.token_urlsafe(32)
    monkeypatch.setenv("EASIFA_SESSION_KEY", key)
    monkeypatch.setenv("EASIFA_MCP_SESSION_FILE", str(path))
    config = EasifaMCPSettings.from_env()
    assert config.session_file == path
    assert load_owner_key(config) == key
    assert key not in repr(config)
    assert path.read_text() == "keep this existing file"


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"format":"wrong"}',
    '{"format":"easifa-access","version":1,"token":"too-short"}'])
def test_invalid_existing_file_is_not_replaced(tmp_path, content):
    path = tmp_path / "session.json"
    path.write_text(content)
    path.chmod(0o600)
    with pytest.raises(RuntimeError, match="Preserve the file"):
        load_owner_key(settings(session_file=path))
    assert path.read_text() == content


@pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")
def test_publicly_readable_file_fails_without_rotating_identity():
    config = settings()
    key = load_owner_key(config)
    config.owner_file().chmod(0o644)
    with pytest.raises(RuntimeError, match="permissions"):
        load_owner_key(config)
    config.owner_file().chmod(0o600)
    assert load_owner_key(config) == key


def test_cannot_persist_fails_before_any_requests(tmp_path, monkeypatch):
    parent = tmp_path / "not-a-directory"
    parent.write_text("original")
    def unexpected_client(*args, **kwargs):
        pytest.fail("HTTP client must not start without a durable identity")
    monkeypatch.setattr(httpx, "AsyncClient", unexpected_client)
    with pytest.raises(RuntimeError, match="identity"):
        EasifaAgentClient(settings(session_file=parent / "session.json"))
    assert parent.read_text() == "original"


@pytest.mark.parametrize("key", ["", "short", "!" * 43, "a" * 129])
def test_invalid_explicit_key_is_rejected_without_echo(key):
    with pytest.raises(ValueError, match="Invalid EasIFA owner key") as error:
        load_owner_key(settings(session_key=key))
    if key:
        assert key not in str(error.value)


def test_fallback_order_keeps_profile_and_deployments_are_separate():
    config = settings(backend_base_urls=("https://a.example/easifa", "https://b.example/easifa/"))
    reordered = replace(config, backend_base_urls=tuple(reversed(config.backend_base_urls)))
    assert config.owner_file() == reordered.owner_file()
    assert load_owner_key(config) == load_owner_key(reordered)
    assert settings().owner_file() != config.owner_file()


def test_gateway_submission_backend_read_restart_and_wrong_owner():
    owners = {}
    config = settings(bearer_token="gateway-service-token")
    def handler(request):
        owner = request.headers.get("X-Easifa-Session")
        if request.url.path.endswith("/batch-analyze"):
            assert request.headers["Authorization"] == "Bearer gateway-service-token"
            owners["private-job"] = owner
            return httpx.Response(200, json={"job_id": "private-job", "status": "completed"},
                                  headers={"Set-Cookie": "easifa_session=different-gateway-cookie; Path=/"})
        assert "Authorization" not in request.headers
        if owner and owner == owners.get("private-job"):
            return httpx.Response(200, json={"job_id": "private-job", "status": "completed"})
        return httpx.Response(404, json={"detail": "Job not found"})

    async def read_as(config, submit=False):
        async with httpx.AsyncClient(base_url=config.agent_base_url, transport=httpx.MockTransport(handler)) as gateway, \
                   httpx.AsyncClient(base_url=config.backend_base_url, transport=httpx.MockTransport(handler),
                                     cookies={"easifa_session": "different-backend-cookie"}) as backend:
            client = EasifaAgentClient(config, agent_client=gateway, backend_client=backend)
            if submit:
                await client.batch_analyze(data=[{"uniprot_id": "P12345"}])
            return await client.get_prediction_result(job_id="private-job")

    first = asyncio.run(read_as(config, submit=True))
    assert first["status"] == "completed"
    assert asyncio.run(read_as(config)) == first
    with pytest.raises(RuntimeError, match="HTTP 404"):
        asyncio.run(read_as(replace(config, session_key=secrets.token_urlsafe(32))))


def test_both_services_fallback_with_original_identity(monkeypatch):
    calls = []
    async def fake_request(self, method, url, **kwargs):
        request = httpx.Request(method, str(self.base_url).rstrip("/") + url, headers=kwargs["headers"])
        calls.append(request)
        assert kwargs["follow_redirects"] is False
        if request.url.host == "down.example":
            raise httpx.ConnectError("unavailable", request=request)
        return httpx.Response(200, request=request, json={"status": "completed", "job_id": "private-job"})
    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    config = settings(
        bearer_token="gateway-only",
        agent_base_urls=("https://down.example/agent", "https://ok.example/agent"),
        backend_base_urls=("https://down.example/easifa", "https://ok.example/easifa"),
    )
    async def run():
        client = EasifaAgentClient(config)
        try:
            await client.batch_analyze(data=[{"uniprot_id": "P12345"}])
            await client.get_prediction_result(job_id="private-job")
        finally:
            await client.aclose()
    asyncio.run(run())
    assert len(calls) == 4
    assert {r.headers["X-Easifa-Session"] for r in calls} == {load_owner_key(config)}
    assert all(r.headers["Authorization"] == "Bearer gateway-only" for r in calls[:2])
    assert all("Authorization" not in r.headers for r in calls[2:])


def test_share_is_explicit_task_scoped_and_revocable():
    requests = []
    share_token = secrets.token_urlsafe(32)
    config = settings()
    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"share_url": f"/easifa/results/private-job#share={share_token}"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"revoked": True})
        return httpx.Response(200, json={"status": "completed"})
    async def run():
        async with httpx.AsyncClient(base_url=config.backend_base_url, transport=httpx.MockTransport(handler)) as http:
            client = EasifaAgentClient(config, agent_client=http, backend_client=http)
            result = await client.get_prediction_result(job_id="private-job")
            assert result["result_endpoint"] == "https://web.example/easifa/results/private-job"
            assert [r.method for r in requests] == ["GET"]
            shared = await client.create_job_share_link(job_id="private-job")
            assert shared["share_url"] == f"https://web.example/easifa/results/private-job#share={share_token}"
            assert load_owner_key(config) not in json.dumps(shared)
            assert (await client.revoke_job_share_link(job_id="private-job"))["revoked"] is True
    asyncio.run(run())
    assert [r.method for r in requests] == ["GET", "POST", "DELETE"]
    assert all(r.url.path == "/easifa/api/job/private-job/share" for r in requests[1:])
    assert all(r.headers["X-Easifa-Session"] == load_owner_key(config) for r in requests)


@pytest.mark.parametrize("link", ["", "/results/other-job#share=" + "s" * 43,
    "/results/private-job?owner=secret#share=" + "s" * 43,
    "/results/private-job#share=short", "/results/private-job#share=" + "s" * 43 + "&owner=secret"])
def test_malformed_share_response_is_rejected(link):
    async def run():
        async with httpx.AsyncClient(base_url="https://backend.example", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"share_url": link}))) as http:
            client = EasifaAgentClient(settings(), agent_client=http, backend_client=http)
            with pytest.raises(RuntimeError, match="invalid task sharing link"):
                await client.create_job_share_link(job_id="private-job")
    asyncio.run(run())


def test_redirect_does_not_forward_owner_credentials():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "https://unrelated.example/results"})
    async def run():
        async with httpx.AsyncClient(base_url="https://backend.example", follow_redirects=True,
                                    transport=httpx.MockTransport(handler)) as http:
            client = EasifaAgentClient(settings(), agent_client=http, backend_client=http)
            with pytest.raises(RuntimeError, match="HTTP 307"):
                await client.get_prediction_result(job_id="private-job")
    asyncio.run(run())
    assert len(calls) == 1
    assert calls[0].url.host == "backend.example"
