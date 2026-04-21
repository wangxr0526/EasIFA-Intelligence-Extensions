from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

DEFAULT_LOCAL_BASE_URL = "http://localhost:8011/easifa-agent"
DEFAULT_LOCAL_BACKEND_BASE_URL = "http://localhost:8006/easifa"
DEFAULT_LOCAL_PUBLIC_API_BASE_URL = "http://127.0.0.1:3000/easifa/api"
DEFAULT_TIMEOUT_SECONDS = 120.0
LEGACY_AGENT_PATH = "/easifa-agent"
PUBLIC_AGENT_PATH = "/easifa/agent"
PUBLIC_BACKEND_PATH = "/easifa"
PUBLIC_API_PATH = "/easifa/api"
DEFAULT_PUBLIC_API_BASE_URLS = (
    "https://cadd.drugflow.com/easifa/api",
    "https://cadd.zju.edu.cn/easifa/api",
    "http://cadd.iddd.group/easifa/api",
)
LOCAL_STAGE_NAMES = {"local", "dev", "debug", "test", "testing"}
PUBLIC_STAGE_NAMES = {"prod", "production", "release", "online"}


def _normalize_http_url(raw_url: str, *, env_name: str, example_url: str) -> tuple[str, object]:
    base_url = (raw_url or "").strip().rstrip("/")
    if not base_url:
        raise ValueError(f"{env_name} cannot be empty")

    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"{env_name} must be a valid http(s) URL, "
            f"for example {example_url}",
        )

    return base_url, parsed


def _replace_path(parsed, path: str) -> str:
    normalized_path = path or "/"
    return urlunparse((parsed.scheme, parsed.netloc, normalized_path, "", "", ""))


def _dedupe_urls(urls: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(urls))


def _split_url_list(raw_urls: str | None) -> list[str]:
    if not raw_urls:
        return []
    tokens: list[str] = []
    for chunk in raw_urls.replace("\n", ",").split(","):
        token = chunk.strip()
        if token:
            tokens.append(token)
    return tokens


def _is_truthy(raw_value: str | None) -> bool:
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_default_public_api_urls() -> tuple[str, ...]:
    configured_stage = str(os.getenv("EASIFA_MCP_STAGE") or "").strip().lower()
    if configured_stage in LOCAL_STAGE_NAMES:
        return (DEFAULT_LOCAL_PUBLIC_API_BASE_URL,)
    if configured_stage in PUBLIC_STAGE_NAMES:
        return DEFAULT_PUBLIC_API_BASE_URLS
    if _is_truthy(os.getenv("EASIFA_DEBUG")):
        return (DEFAULT_LOCAL_PUBLIC_API_BASE_URL,)
    return DEFAULT_PUBLIC_API_BASE_URLS


def normalize_public_api_base_url(raw_base_url: str) -> str:
    _base_url, parsed = _normalize_http_url(
        raw_base_url,
        env_name="EASIFA_PUBLIC_API_BASE_URLS",
        example_url="https://cadd.drugflow.com/easifa/api",
    )
    normalized_path = parsed.path.rstrip("/")
    if normalized_path in {"", "/"}:
        return _replace_path(parsed, PUBLIC_API_PATH)
    if normalized_path == PUBLIC_BACKEND_PATH:
        return _replace_path(parsed, PUBLIC_API_PATH)
    if normalized_path.endswith("/api"):
        return _replace_path(parsed, normalized_path)
    return _replace_path(parsed, PUBLIC_API_PATH)


def public_api_to_web_base_url(public_api_base_url: str) -> str:
    parsed = urlparse(normalize_public_api_base_url(public_api_base_url))
    normalized_path = parsed.path.rstrip("/")
    if normalized_path.endswith("/api"):
        normalized_path = normalized_path[: -len("/api")] or "/"
    return _replace_path(parsed, normalized_path)


def public_api_to_agent_base_url(public_api_base_url: str) -> str:
    parsed = urlparse(public_api_to_web_base_url(public_api_base_url))
    return _replace_path(parsed, PUBLIC_AGENT_PATH)


def normalize_agent_base_url(raw_base_url: str) -> str:
    base_url, parsed = _normalize_http_url(
        raw_base_url,
        env_name="EASIFA_AGENT_BASE_URL",
        example_url="http://localhost:8011/easifa-agent",
    )
    normalized_path = parsed.path.rstrip("/")

    if normalized_path in {"", "/"}:
        return f"{base_url}{LEGACY_AGENT_PATH}"
    if normalized_path == PUBLIC_BACKEND_PATH:
        return _replace_path(parsed, PUBLIC_AGENT_PATH)
    if normalized_path == PUBLIC_API_PATH:
        return _replace_path(parsed, PUBLIC_AGENT_PATH)
    return _replace_path(parsed, normalized_path)


def normalize_backend_base_url(raw_base_url: str) -> str:
    base_url, parsed = _normalize_http_url(
        raw_base_url,
        env_name="EASIFA_BACKEND_BASE_URL",
        example_url="http://localhost:8006/easifa",
    )
    normalized_path = parsed.path.rstrip("/")

    if normalized_path in {"", "/"}:
        return f"{base_url}{PUBLIC_BACKEND_PATH}"
    if normalized_path.endswith("/api"):
        normalized_path = normalized_path[: -len("/api")] or "/"
    return _replace_path(parsed, normalized_path)


def normalize_public_web_base_url(raw_base_url: str) -> str:
    return normalize_backend_base_url(raw_base_url)


def derive_backend_base_url(agent_base_url: str) -> str:
    normalized_agent_base_url = normalize_agent_base_url(agent_base_url)
    parsed = urlparse(normalized_agent_base_url)
    normalized_path = parsed.path.rstrip("/")

    if (
        parsed.hostname in {"localhost", "127.0.0.1"}
        and parsed.port == 8011
        and normalized_path in {LEGACY_AGENT_PATH, PUBLIC_AGENT_PATH}
    ):
        return normalize_backend_base_url(
            urlunparse((parsed.scheme, f"{parsed.hostname}:8006", PUBLIC_BACKEND_PATH, "", "", ""))
        )

    if normalized_path in {LEGACY_AGENT_PATH, PUBLIC_AGENT_PATH}:
        return normalize_backend_base_url(_replace_path(parsed, PUBLIC_BACKEND_PATH))
    if normalized_path in {"", "/"}:
        return normalize_backend_base_url(_replace_path(parsed, PUBLIC_BACKEND_PATH))
    if normalized_path == PUBLIC_BACKEND_PATH:
        return normalize_backend_base_url(normalized_agent_base_url)

    return normalize_backend_base_url(_replace_path(parsed, PUBLIC_BACKEND_PATH))


@dataclass(frozen=True)
class EasifaMCPSettings:
    agent_base_url: str = DEFAULT_LOCAL_BASE_URL
    backend_base_url: str = DEFAULT_LOCAL_BACKEND_BASE_URL
    agent_base_urls: tuple[str, ...] = ()
    backend_base_urls: tuple[str, ...] = ()
    public_api_base_urls: tuple[str, ...] = DEFAULT_PUBLIC_API_BASE_URLS
    public_web_base_url: str | None = None
    public_agent_base_url: str | None = None
    bearer_token: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None = None,
        backend_base_url: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float | None = None,
    ) -> "EasifaMCPSettings":
        configured_public_api_urls = _split_url_list(os.getenv("EASIFA_PUBLIC_API_BASE_URLS"))
        if not configured_public_api_urls:
            configured_public_api_urls = list(_resolve_default_public_api_urls())
        resolved_public_api_base_urls = _dedupe_urls(
            [normalize_public_api_base_url(url) for url in configured_public_api_urls]
        )

        explicit_agent_base_url = base_url or os.getenv("EASIFA_AGENT_BASE_URL")
        explicit_backend_base_url = backend_base_url or os.getenv("EASIFA_BACKEND_BASE_URL")

        resolved_base_url = normalize_agent_base_url(
            explicit_agent_base_url
            or public_api_to_agent_base_url(resolved_public_api_base_urls[0]),
        )
        resolved_backend_base_url = normalize_backend_base_url(
            explicit_backend_base_url
            or public_api_to_web_base_url(resolved_public_api_base_urls[0]),
        )

        resolved_agent_base_urls = _dedupe_urls(
            [resolved_base_url]
            + (
                []
                if explicit_agent_base_url
                else [public_api_to_agent_base_url(url) for url in resolved_public_api_base_urls]
            )
        )
        resolved_backend_base_urls = _dedupe_urls(
            [resolved_backend_base_url]
            + (
                []
                if explicit_backend_base_url
                else [public_api_to_web_base_url(url) for url in resolved_public_api_base_urls]
            )
        )

        resolved_public_web_base_url = normalize_public_web_base_url(
            os.getenv("EASIFA_PUBLIC_WEB_BASE_URL")
            or public_api_to_web_base_url(resolved_public_api_base_urls[0]),
        )
        resolved_public_agent_base_url = normalize_agent_base_url(
            os.getenv("EASIFA_PUBLIC_AGENT_BASE_URL")
            or public_api_to_agent_base_url(resolved_public_api_base_urls[0]),
        )

        resolved_token = bearer_token
        if resolved_token is None:
            resolved_token = os.getenv("EASIFA_AGENT_BEARER_TOKEN") or None
        resolved_token = resolved_token.strip() if resolved_token else None

        if timeout_seconds is None:
            timeout_seconds = float(os.getenv("EASIFA_AGENT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        timeout_seconds = max(1.0, float(timeout_seconds))

        return cls(
            agent_base_url=resolved_base_url,
            backend_base_url=resolved_backend_base_url,
            agent_base_urls=resolved_agent_base_urls,
            backend_base_urls=resolved_backend_base_urls,
            public_api_base_urls=resolved_public_api_base_urls,
            public_web_base_url=resolved_public_web_base_url,
            public_agent_base_url=resolved_public_agent_base_url,
            bearer_token=resolved_token,
            timeout_seconds=timeout_seconds,
        )
