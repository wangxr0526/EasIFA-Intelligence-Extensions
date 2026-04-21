from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

from .config import EasifaMCPSettings


class EasifaAgentClient:
    def __init__(
        self,
        settings: EasifaMCPSettings,
        *,
        agent_client: httpx.AsyncClient | None = None,
        backend_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_agent_clients = agent_client is None
        self._owns_backend_clients = backend_client is None
        self._agent_base_urls = settings.agent_base_urls or (settings.agent_base_url,)
        self._backend_base_urls = settings.backend_base_urls or (settings.backend_base_url,)
        self._agent_clients = (
            [agent_client]
            if agent_client is not None
            else [
                httpx.AsyncClient(
                    base_url=base_url,
                    timeout=settings.timeout_seconds,
                    headers={"Accept": "application/json"},
                )
                for base_url in self._agent_base_urls
            ]
        )
        self._backend_clients = (
            [backend_client]
            if backend_client is not None
            else [
                httpx.AsyncClient(
                    base_url=base_url,
                    timeout=settings.timeout_seconds,
                    headers={"Accept": "application/json"},
                )
                for base_url in self._backend_base_urls
            ]
        )

    async def aclose(self) -> None:
        if self._owns_agent_clients:
            for client in self._agent_clients:
                await client.aclose()
        if self._owns_backend_clients:
            for client in self._backend_clients:
                await client.aclose()

    async def query_uniprot(self, *, enzyme_name: str, size: int = 5) -> dict[str, Any]:
        return await self._post_agent_json("/query-uniprot", {"enzyme_name": enzyme_name, "size": size})

    async def query_uniprot_sites(self, *, uniprot_id: str) -> dict[str, Any]:
        return await self._post_agent_json("/query-uniprot-sites", {"uniprot_id": uniprot_id})

    async def batch_analyze(
        self,
        *,
        data: list[dict[str, str]],
        timeout: int = 600,
        poll_interval: int = 2,
    ) -> dict[str, Any]:
        return await self._post_agent_json(
            "/batch-analyze",
            {"data": data, "timeout": timeout, "poll_interval": poll_interval},
        )

    async def batch_analyze_sequences(
        self,
        *,
        data: list[dict[str, Any]],
        timeout: int = 600,
        poll_interval: int = 2,
    ) -> dict[str, Any]:
        return await self._post_agent_json(
            "/batch-analyze-sequences",
            {"data": data, "timeout": timeout, "poll_interval": poll_interval},
        )

    async def submit_structure_prediction(
        self,
        *,
        pdb_file_path: str,
        rxn_smiles: str | None = None,
    ) -> dict[str, Any]:
        pdb_path = Path(pdb_file_path).expanduser()
        if not pdb_path.exists() or not pdb_path.is_file():
            raise RuntimeError(f"PDB file does not exist: {pdb_path}")
        if pdb_path.suffix.lower() != ".pdb":
            raise RuntimeError(f"PDB file must end with .pdb: {pdb_path}")

        form_data: dict[str, str] = {}
        if rxn_smiles:
            form_data["rxn_smiles"] = rxn_smiles

        file_bytes = pdb_path.read_bytes()
        return await self._request_json(
            clients=self._backend_clients,
            endpoint="/api/from_structure",
            service_label="EasIFA backend",
            config_hint_name="EASIFA_BACKEND_BASE_URL",
            method="POST",
            public_base_url_for_errors=self._frontend_base_url(),
            data=form_data,
            files={"pdb_file": (pdb_path.name, file_bytes, "chemical/x-pdb")},
        )

    async def get_prediction_result(self, *, job_id: str, slim: bool = True) -> dict[str, Any]:
        normalized_job_id = str(job_id or "").strip()
        if not normalized_job_id:
            raise RuntimeError("job_id cannot be empty")
        return await self._request_json(
            clients=self._backend_clients,
            endpoint=f"/api/results/{normalized_job_id}",
            service_label="EasIFA backend",
            config_hint_name="EASIFA_BACKEND_BASE_URL",
            method="GET",
            public_base_url_for_errors=self._frontend_base_url(),
            params={"slim": "true" if slim else "false"},
        )

    async def analyze_structure(
        self,
        *,
        pdb_file_path: str,
        rxn_smiles: str | None = None,
        timeout: int = 600,
        poll_interval: int = 2,
        slim: bool = True,
    ) -> dict[str, Any]:
        submission = await self.submit_structure_prediction(
            pdb_file_path=pdb_file_path,
            rxn_smiles=rxn_smiles,
        )
        job_id = str(submission.get("job_id") or "").strip()
        if not job_id:
            raise RuntimeError("Backend response missing job_id for structure submission")

        timeout = max(30, int(timeout))
        poll_interval = max(0.0, float(poll_interval))
        deadline = time.monotonic() + timeout
        last_payload: dict[str, Any] | None = None
        submission_endpoint = self._frontend_submission_url(submission_mode="api_from_structure")

        while time.monotonic() < deadline:
            try:
                payload = await self.get_prediction_result(job_id=job_id, slim=slim)
            except RuntimeError as exc:
                return {
                    "status": "failed",
                    "submission_mode": "api_from_structure",
                    "submission_endpoint": submission_endpoint,
                    "result_endpoint": self._frontend_job_status_url(job_id),
                    "job_id": job_id,
                    "result": None,
                    "error": str(exc),
                }

            last_payload = payload
            if payload.get("status") == "completed":
                return {
                    "status": "completed",
                    "submission_mode": "api_from_structure",
                    "submission_endpoint": submission_endpoint,
                    "result_endpoint": self._frontend_result_url(job_id),
                    "job_id": job_id,
                    "result": payload,
                    "error": None,
                }

            await asyncio.sleep(poll_interval)

        return {
            "status": "failed",
            "submission_mode": "api_from_structure",
            "submission_endpoint": submission_endpoint,
            "result_endpoint": self._frontend_job_status_url(job_id),
            "job_id": job_id,
            "result": last_payload,
            "error": "Timed out waiting for structure prediction result",
        }

    def _frontend_base_url(self) -> str:
        if self._settings.public_web_base_url:
            return str(self._settings.public_web_base_url).rstrip("/")
        if self._settings.public_api_base_urls:
            return str(self._settings.public_api_base_urls[0]).rstrip("/")[: -len("/api")]
        return str(self._settings.backend_base_url).rstrip("/")

    def _public_agent_base_url(self) -> str:
        if self._settings.public_agent_base_url:
            return str(self._settings.public_agent_base_url).rstrip("/")
        if self._settings.public_api_base_urls:
            return f"{str(self._settings.public_api_base_urls[0]).rstrip('/')[: -len('/api')]}/agent"
        return str(self._settings.agent_base_url).rstrip("/")

    def _frontend_submission_url(self, *, submission_mode: str) -> str:
        page_by_mode = {
            "api_from_structure": "/from-structure",
            "api_from_sequence": "/from-structure",
            "api_from_uniprot": "/from-uniprot",
        }
        page_path = page_by_mode.get(submission_mode, "/")
        return f"{self._frontend_base_url()}{page_path}"

    def _frontend_result_url(self, job_id: str) -> str:
        return f"{self._frontend_base_url()}/results/{job_id}"

    def _frontend_job_status_url(self, job_id: str) -> str:
        return f"{self._frontend_base_url()}/job-status?jobId={job_id}"

    def _rewrite_public_endpoints(self, payload: dict[str, Any]) -> dict[str, Any]:
        rewritten = dict(payload)
        submission_mode = str(rewritten.get("submission_mode") or "").strip()
        job_id = str(rewritten.get("job_id") or "").strip()
        status = str(rewritten.get("status") or "").strip().lower()

        if rewritten.get("submission_endpoint") and submission_mode:
            rewritten["submission_endpoint"] = self._frontend_submission_url(
                submission_mode=submission_mode,
            )

        if rewritten.get("result_endpoint") and job_id:
            rewritten["result_endpoint"] = (
                self._frontend_result_url(job_id)
                if status == "completed"
                else self._frontend_job_status_url(job_id)
            )

        if rewritten.get("poll_url") and job_id:
            rewritten["poll_url"] = f"{self._public_agent_base_url()}/http/jobs/{job_id}"

        if rewritten.get("result_url") and job_id:
            rewritten["result_url"] = f"{self._public_agent_base_url()}/http/jobs/{job_id}/result"

        return rewritten

    async def _post_agent_json(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if self._settings.bearer_token:
            headers["Authorization"] = f"Bearer {self._settings.bearer_token}"
        response_payload = await self._request_json(
            clients=self._agent_clients,
            endpoint=endpoint,
            service_label="EasIFA Agent Gateway",
            config_hint_name="EASIFA_AGENT_BASE_URL",
            method="POST",
            public_base_url_for_errors=self._public_agent_base_url(),
            json=payload,
            headers=headers or None,
        )
        return self._rewrite_public_endpoints(response_payload)

    async def _request_json(
        self,
        *,
        clients: list[httpx.AsyncClient],
        endpoint: str,
        service_label: str,
        config_hint_name: str,
        method: str,
        public_base_url_for_errors: str,
        **request_kwargs: Any,
    ) -> dict[str, Any]:
        errors: list[str] = []
        for index, client in enumerate(clients):
            is_last = index == len(clients) - 1
            try:
                response = await client.request(method, endpoint, **request_kwargs)
                response.raise_for_status()
            except httpx.TimeoutException as exc:
                message = (
                    f"Request to {public_base_url_for_errors.rstrip('/')}{endpoint} timed out after "
                    f"{self._settings.timeout_seconds:.0f}s. You can raise the timeout via "
                    f"{config_hint_name} or EASIFA_AGENT_TIMEOUT_SECONDS if needed."
                )
                if is_last:
                    raise RuntimeError(_combine_fallback_errors(errors + [message])) from exc
                errors.append(message)
                continue
            except httpx.HTTPStatusError as exc:
                message = _build_http_error_message(
                    exc.response,
                    service_label=service_label,
                    config_hint_name=config_hint_name,
                    public_base_url_for_errors=public_base_url_for_errors,
                )
                if is_last or not _should_try_next_base_url(exc.response.status_code):
                    raise RuntimeError(_combine_fallback_errors(errors + [message])) from exc
                errors.append(message)
                continue
            except httpx.HTTPError as exc:
                message = (
                    f"Failed to connect to {service_label} via {public_base_url_for_errors}. "
                    f"Please check {config_hint_name} and your network connectivity."
                )
                if is_last:
                    raise RuntimeError(_combine_fallback_errors(errors + [message])) from exc
                errors.append(message)
                continue

            try:
                payload_json = response.json()
            except ValueError as exc:
                message = (
                    f"{response.request.method} {public_base_url_for_errors.rstrip('/')}{endpoint} returned "
                    f"a non-JSON response, which is unexpected for {service_label}."
                )
                if is_last:
                    raise RuntimeError(_combine_fallback_errors(errors + [message])) from exc
                errors.append(message)
                continue

            if not isinstance(payload_json, dict):
                message = (
                    f"{response.request.method} {public_base_url_for_errors.rstrip('/')}{endpoint} returned "
                    f"{type(payload_json).__name__}, but a JSON object was expected."
                )
                if is_last:
                    raise RuntimeError(_combine_fallback_errors(errors + [message]))
                errors.append(message)
                continue
            return payload_json

        raise RuntimeError(_combine_fallback_errors(errors))


def _build_http_error_message(
    response: httpx.Response,
    *,
    service_label: str,
    config_hint_name: str,
    public_base_url_for_errors: str,
) -> str:
    detail = _extract_error_detail(response)
    hint = ""
    if response.status_code in {401, 403}:
        hint = " Check EASIFA_AGENT_BEARER_TOKEN if the gateway is protected."
    elif response.status_code == 404:
        hint = (
            f" Check whether {config_hint_name} points to the correct service root, "
            "for example https://your-server.example.com/easifa/agent "
            "or https://your-server.example.com/easifa."
        )
    elif response.status_code >= 500:
        hint = f" {service_label} may be unavailable on the target server."

    return (
        f"{response.request.method} {public_base_url_for_errors.rstrip('/')}{response.request.url.path} "
        f"returned HTTP {response.status_code}: "
        f"{detail}.{hint}"
    )


def _should_try_next_base_url(status_code: int) -> bool:
    return status_code in {404, 408, 429} or status_code >= 500


def _combine_fallback_errors(errors: list[str]) -> str:
    compact_errors = [item.strip() for item in errors if item and item.strip()]
    if not compact_errors:
        return "All configured EasIFA endpoints failed."
    if len(compact_errors) == 1:
        return compact_errors[0]
    return "All configured EasIFA endpoints failed. " + " | ".join(compact_errors)


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or "empty response body"

    if isinstance(payload, dict):
        for key in ("detail", "error", "message"):
            value = payload.get(key)
            if value:
                return str(value)
        return json.dumps(payload, ensure_ascii=True)

    return json.dumps(payload, ensure_ascii=True)
