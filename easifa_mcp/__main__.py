from __future__ import annotations

import argparse

from .config import (
    DEFAULT_LOCAL_PUBLIC_API_BASE_URL,
    DEFAULT_PUBLIC_API_BASE_URLS,
    EasifaMCPSettings,
)
from .server import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="easifa-mcp",
        description="Local MCP server that proxies EasIFA Agent Gateway HTTP endpoints.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "EasIFA Agent Gateway base URL. "
            "If you pass a public EasIFA base like https://host/easifa, "
            "it will be expanded to https://host/easifa/agent automatically. "
            "If omitted, defaults switch automatically: "
            f"testing uses {DEFAULT_LOCAL_PUBLIC_API_BASE_URL[:-len('/api')]}, "
            f"production uses {DEFAULT_PUBLIC_API_BASE_URLS[0][:-len('/api')]}."
        ),
    )
    parser.add_argument(
        "--backend-base-url",
        default=None,
        help=(
            "Optional EasIFA backend base URL for structure submission and result retrieval. "
            "If omitted, it is derived automatically from the agent base URL. "
            "Testing defaults to http://127.0.0.1:3000/easifa; "
            f"production defaults to {DEFAULT_PUBLIC_API_BASE_URLS[0][:-len('/api')]}."
        ),
    )
    parser.add_argument(
        "--bearer-token",
        default=None,
        help="Optional bearer token for protected EasIFA Agent Gateway deployments.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=None,
        help="HTTP timeout in seconds. Default from EASIFA_AGENT_TIMEOUT_SECONDS or 120.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = EasifaMCPSettings.from_env(
        base_url=args.base_url,
        backend_base_url=args.backend_base_url,
        bearer_token=args.bearer_token,
        timeout_seconds=args.timeout_seconds,
    )
    run_server(settings)


if __name__ == "__main__":
    main()
