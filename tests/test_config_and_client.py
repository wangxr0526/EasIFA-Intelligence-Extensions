from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from easifa_mcp.client import EasifaAgentClient
from easifa_mcp.config import (
    DEFAULT_PUBLIC_API_BASE_URLS,
    EasifaMCPSettings,
    derive_backend_base_url,
    normalize_agent_base_url,
)


def test_normalize_agent_base_url_appends_gateway_path():
    assert normalize_agent_base_url("https://example.com") == "https://example.com/easifa-agent"


def test_normalize_agent_base_url_expands_public_easifa_path():
    assert normalize_agent_base_url("https://example.com/easifa") == "https://example.com/easifa/agent"


def test_normalize_agent_base_url_preserves_explicit_path():
    assert (
        normalize_agent_base_url("https://example.com/easifa-agent/")
        == "https://example.com/easifa-agent"
    )


def test_derive_backend_base_url_rewrites_agent_path():
    assert derive_backend_base_url("https://example.com/easifa-agent") == "https://example.com/easifa"


def test_derive_backend_base_url_rewrites_public_agent_path():
    assert derive_backend_base_url("https://example.com/easifa/agent") == "https://example.com/easifa"


def test_derive_backend_base_url_uses_local_backend_port_for_localhost():
    assert derive_backend_base_url("http://127.0.0.1:8011/easifa-agent") == "http://127.0.0.1:8006/easifa"


def test_from_env_uses_local_3000_profile_when_debug_enabled(monkeypatch):
    monkeypatch.setenv("EASIFA_DEBUG", "true")
    monkeypatch.delenv("EASIFA_PUBLIC_API_BASE_URLS", raising=False)
    monkeypatch.delenv("EASIFA_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("EASIFA_BACKEND_BASE_URL", raising=False)

    settings = EasifaMCPSettings.from_env()

    assert settings.agent_base_url == "http://127.0.0.1:3000/easifa/agent"
    assert settings.backend_base_url == "http://127.0.0.1:3000/easifa"
    assert settings.public_web_base_url == "http://127.0.0.1:3000/easifa"


def test_from_env_uses_public_fallback_domains_by_default(monkeypatch):
    monkeypatch.delenv("EASIFA_DEBUG", raising=False)
    monkeypatch.delenv("EASIFA_MCP_STAGE", raising=False)
    monkeypatch.delenv("EASIFA_PUBLIC_API_BASE_URLS", raising=False)
    monkeypatch.delenv("EASIFA_AGENT_BASE_URL", raising=False)
    monkeypatch.delenv("EASIFA_BACKEND_BASE_URL", raising=False)

    settings = EasifaMCPSettings.from_env()

    assert settings.public_api_base_urls == DEFAULT_PUBLIC_API_BASE_URLS
    assert settings.backend_base_urls == (
        "https://cadd.drugflow.com/easifa",
        "https://cadd.zju.edu.cn/easifa",
        "http://cadd.iddd.group/easifa",
    )
    assert settings.agent_base_urls == (
        "https://cadd.drugflow.com/easifa/agent",
        "https://cadd.zju.edu.cn/easifa/agent",
        "http://cadd.iddd.group/easifa/agent",
    )
    assert settings.public_web_base_url == "https://cadd.drugflow.com/easifa"


def test_query_uniprot_forwards_payload_and_bearer_token():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"status": "success", "items": ["P12345"]})

    async def run() -> None:
        settings = EasifaMCPSettings(
            agent_base_url="https://example.com/easifa-agent",
            backend_base_url="https://example.com/easifa",
            bearer_token="secret-token",
            timeout_seconds=30,
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://example.com/easifa-agent",
        ) as http_client:
            client = EasifaAgentClient(settings, agent_client=http_client)
            payload = await client.query_uniprot(enzyme_name="lipase", size=3)
            assert payload == {"status": "success", "items": ["P12345"]}

    asyncio.run(run())

    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.com/easifa-agent/query-uniprot"
    assert captured["authorization"] == "Bearer secret-token"
    assert json.loads(str(captured["body"])) == {"enzyme_name": "lipase", "size": 3}


def test_batch_analyze_sequences_forwards_nested_data():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "submission_mode": "api_from_sequence",
                "submission_endpoint": "http://internal:8006/easifa/api/from_sequence",
                "results": [],
            },
        )

    async def run() -> None:
        settings = EasifaMCPSettings(
            agent_base_url="http://localhost:8011/easifa-agent",
            backend_base_url="http://localhost:8006/easifa",
            public_web_base_url="http://127.0.0.1:3000/easifa",
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://localhost:8011/easifa-agent",
        ) as http_client:
            client = EasifaAgentClient(settings, agent_client=http_client)
            payload = await client.batch_analyze_sequences(
                data=[{"aa_sequence": "MKTAYIAK", "rxn_smiles": None}],
                timeout=222,
                poll_interval=3,
            )
            assert payload["status"] == "completed"
            assert payload["submission_endpoint"] == "http://127.0.0.1:3000/easifa/from-structure"

    asyncio.run(run())

    assert captured["url"] == "http://localhost:8011/easifa-agent/batch-analyze-sequences"
    assert json.loads(str(captured["body"])) == {
        "data": [{"aa_sequence": "MKTAYIAK", "rxn_smiles": None}],
        "timeout": 222,
        "poll_interval": 3,
    }


def test_batch_analyze_rewrites_public_agent_job_urls():
    async def run() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "pending",
                    "job_id": "agent-job-1",
                    "poll_url": "http://internal:8011/easifa-agent/http/jobs/agent-job-1",
                    "result_url": "http://internal:8011/easifa-agent/http/jobs/agent-job-1/result",
                },
            )

        settings = EasifaMCPSettings(
            agent_base_url="http://10.0.0.8:8011/easifa-agent",
            backend_base_url="http://10.0.0.8:8006/easifa",
            public_web_base_url="https://cadd.drugflow.com/easifa",
            public_agent_base_url="https://cadd.drugflow.com/easifa/agent",
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://10.0.0.8:8011/easifa-agent",
        ) as http_client:
            client = EasifaAgentClient(settings, agent_client=http_client)
            payload = await client.batch_analyze(data=[{"uniprot_id": "P12345"}])
            assert payload["poll_url"] == "https://cadd.drugflow.com/easifa/agent/http/jobs/agent-job-1"
            assert payload["result_url"] == "https://cadd.drugflow.com/easifa/agent/http/jobs/agent-job-1/result"

    asyncio.run(run())


def test_http_404_error_message_mentions_gateway_base_url():
    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(404, json={"detail": "Not Found"})

    async def run() -> None:
        settings = EasifaMCPSettings(
            agent_base_url="https://example.com/easifa-agent",
            backend_base_url="https://example.com/easifa",
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://example.com/easifa-agent",
        ) as http_client:
            client = EasifaAgentClient(settings, agent_client=http_client)
            with pytest.raises(RuntimeError) as exc_info:
                await client.query_uniprot_sites(uniprot_id="P12345")

        message = str(exc_info.value)
        assert "HTTP 404" in message
        assert "EASIFA_AGENT_BASE_URL" in message
        assert "easifa/agent" in message

    asyncio.run(run())


def test_query_uniprot_falls_back_to_second_public_domain(monkeypatch):
    calls: list[str] = []

    async def fake_request(self, method, url, **kwargs):
        del kwargs
        calls.append(f"{self.base_url}{url}")
        request = httpx.Request(method, f"{str(self.base_url).rstrip('/')}{url}")
        if "cadd.drugflow.com" in str(self.base_url):
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, request=request, json={"status": "success", "items": ["P12345"]})

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    async def run() -> None:
        settings = EasifaMCPSettings(
            agent_base_url="https://cadd.drugflow.com/easifa/agent",
            backend_base_url="https://cadd.drugflow.com/easifa",
            agent_base_urls=(
                "https://cadd.drugflow.com/easifa/agent",
                "https://cadd.zju.edu.cn/easifa/agent",
                "http://cadd.iddd.group/easifa/agent",
            ),
            backend_base_urls=(
                "https://cadd.drugflow.com/easifa",
                "https://cadd.zju.edu.cn/easifa",
                "http://cadd.iddd.group/easifa",
            ),
            public_web_base_url="https://cadd.drugflow.com/easifa",
            public_agent_base_url="https://cadd.drugflow.com/easifa/agent",
        )
        client = EasifaAgentClient(settings)
        try:
            payload = await client.query_uniprot(enzyme_name="lipase", size=3)
            assert payload["status"] == "success"
        finally:
            await client.aclose()

    asyncio.run(run())

    assert calls[0].replace("//query-uniprot", "/query-uniprot") == "https://cadd.drugflow.com/easifa/agent/query-uniprot"
    assert calls[1].replace("//query-uniprot", "/query-uniprot") == "https://cadd.zju.edu.cn/easifa/agent/query-uniprot"


def test_analyze_structure_submits_file_and_polls_result(tmp_path: Path):
    captured: dict[str, object] = {"poll_count": 0}
    pdb_path = tmp_path / "sample.pdb"
    pdb_path.write_text("HEADER TEST\nATOM      1  N   ALA A   1\n", encoding="utf-8")

    def backend_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/easifa/api/from_structure":
            captured["submit_method"] = request.method
            captured["submit_content_type"] = request.headers.get("Content-Type")
            captured["submit_body"] = request.content.decode("utf-8", errors="ignore")
            return httpx.Response(200, json={"job_id": "job-123", "task_manager": "celery"})
        if request.url.path == "/easifa/api/results/job-123":
            captured["poll_count"] = int(captured["poll_count"]) + 1
            if captured["poll_count"] == 1:
                return httpx.Response(202, json={"status": "pending", "error": "Results are not ready yet"})
            return httpx.Response(
                200,
                json={"status": "completed", "job_id": "job-123", "result_type": "structure"},
            )
        return httpx.Response(404, json={"detail": "Not Found"})

    async def run() -> None:
        settings = EasifaMCPSettings(
            agent_base_url="http://localhost:8011/easifa-agent",
            backend_base_url="http://localhost:8006/easifa",
            public_web_base_url="http://127.0.0.1:3000/easifa",
            timeout_seconds=30,
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(backend_handler),
            base_url="http://localhost:8006/easifa",
        ) as backend_client:
            client = EasifaAgentClient(settings, backend_client=backend_client)
            payload = await client.analyze_structure(
                pdb_file_path=str(pdb_path),
                timeout=30,
                poll_interval=0,
            )
            assert payload["status"] == "completed"
            assert payload["job_id"] == "job-123"
            assert payload["submission_endpoint"] == "http://127.0.0.1:3000/easifa/from-structure"
            assert payload["result_endpoint"] == "http://127.0.0.1:3000/easifa/results/job-123"
            assert payload["result"]["result_type"] == "structure"

    asyncio.run(run())

    assert captured["submit_method"] == "POST"
    assert "multipart/form-data" in str(captured["submit_content_type"])
    assert 'name="pdb_file"' in str(captured["submit_body"])
    assert 'filename="sample.pdb"' in str(captured["submit_body"])
    assert "HEADER TEST" in str(captured["submit_body"])
    assert captured["poll_count"] == 2


def test_analyze_structure_poll_failure_returns_frontend_job_status_url(tmp_path: Path):
    pdb_path = tmp_path / "sample.pdb"
    pdb_path.write_text("HEADER TEST\nATOM      1  N   ALA A   1\n", encoding="utf-8")

    def backend_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/easifa/api/from_structure":
            return httpx.Response(200, json={"job_id": "job-timeout", "task_manager": "celery"})
        return httpx.Response(404, json={"detail": "Not Found"})

    async def run() -> None:
        settings = EasifaMCPSettings(
            agent_base_url="http://localhost:8011/easifa-agent",
            backend_base_url="http://localhost:3000/easifa",
            public_web_base_url="http://localhost:3000/easifa",
            timeout_seconds=30,
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(backend_handler),
            base_url="http://localhost:3000/easifa",
        ) as backend_client:
            client = EasifaAgentClient(settings, backend_client=backend_client)
            payload = await client.analyze_structure(
                pdb_file_path=str(pdb_path),
                timeout=30,
                poll_interval=0,
            )
            assert payload["status"] == "failed"
            assert payload["submission_endpoint"] == "http://localhost:3000/easifa/from-structure"
            assert payload["result_endpoint"] == "http://localhost:3000/easifa/job-status?jobId=job-timeout"
            assert payload["job_id"] == "job-timeout"
            assert "HTTP 404" in payload["error"]

    asyncio.run(run())


def test_get_prediction_result_reads_backend_results_endpoint():
    captured: dict[str, object] = {}

    def backend_handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"status": "completed", "job_id": "job-xyz"})

    async def run() -> None:
        settings = EasifaMCPSettings(
            agent_base_url="http://localhost:8011/easifa-agent",
            backend_base_url="http://localhost:8006/easifa",
        )
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(backend_handler),
            base_url="http://localhost:8006/easifa",
        ) as backend_client:
            client = EasifaAgentClient(settings, backend_client=backend_client)
            payload = await client.get_prediction_result(job_id="job-xyz", slim=True)
            assert payload["status"] == "completed"

    asyncio.run(run())

    assert captured["url"] == "http://localhost:8006/easifa/api/results/job-xyz?slim=true"
