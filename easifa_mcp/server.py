from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import EasifaAgentClient
from .config import EasifaMCPSettings

READ_ONLY_HTTP_TOOL = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

QUERY_UNIPROT_DESCRIPTION = """
Query UniProt candidates from EasIFA Agent Gateway by enzyme name.

This tool forwards to the HTTP endpoint `/query-uniprot`.
""".strip()

QUERY_UNIPROT_SITES_DESCRIPTION = """
Query catalytic or binding site annotations from EasIFA Agent Gateway by UniProt accession.

This tool forwards to the HTTP endpoint `/query-uniprot-sites`.
""".strip()

BATCH_ANALYZE_DESCRIPTION = """
Run UniProt-based batch analysis through EasIFA Agent Gateway.

Use a nested JSON object with a `data` array, for example:
{ "data": [ { "uniprot_id": "P12345" } ] }
""".strip()

BATCH_ANALYZE_SEQUENCES_DESCRIPTION = """
Run sequence-based batch analysis through EasIFA Agent Gateway.

Use a nested JSON object with a `data` array, for example:
{ "data": [ { "aa_sequence": "MKTAYIAK..." } ] }
Optional `rxn_smiles` is supported for each item.
""".strip()

ANALYZE_STRUCTURE_DESCRIPTION = """
Submit one local PDB file to EasIFA backend `/api/from_structure`, then poll until a result is ready.

Use this when you already have a local `.pdb` file and want the MCP server to upload it for prediction.
Parameters:
- `pdb_file_path`: absolute or relative local path to a `.pdb` file
- `rxn_smiles`: optional reaction SMILES
- `timeout`: wait timeout in seconds
- `poll_interval`: polling interval in seconds
- `slim`: whether to request slim result payload from the backend
""".strip()

GET_JOB_RESULT_DESCRIPTION = """
Fetch the current EasIFA prediction result for a submitted job ID.

This tool reads EasIFA backend `/api/results/{job_id}` directly.
If the job is still running, the backend usually returns a JSON status payload.
""".strip()


def create_server(settings: EasifaMCPSettings) -> tuple[FastMCP, EasifaAgentClient]:
    client = EasifaAgentClient(settings)
    mcp = FastMCP("easifa_mcp")

    @mcp.tool(
        name="query-uniprot",
        description=QUERY_UNIPROT_DESCRIPTION,
        annotations=READ_ONLY_HTTP_TOOL,
        structured_output=True,
    )
    async def query_uniprot(enzyme_name: str, size: int = 5) -> dict[str, Any]:
        return await client.query_uniprot(enzyme_name=enzyme_name, size=size)

    @mcp.tool(
        name="query-uniprot-sites",
        description=QUERY_UNIPROT_SITES_DESCRIPTION,
        annotations=READ_ONLY_HTTP_TOOL,
        structured_output=True,
    )
    async def query_uniprot_sites(uniprot_id: str) -> dict[str, Any]:
        return await client.query_uniprot_sites(uniprot_id=uniprot_id)

    @mcp.tool(
        name="batch-analyze",
        description=BATCH_ANALYZE_DESCRIPTION,
        annotations=READ_ONLY_HTTP_TOOL,
        structured_output=True,
    )
    async def batch_analyze(
        data: list[dict[str, str]],
        timeout: int = 600,
        poll_interval: int = 2,
    ) -> dict[str, Any]:
        return await client.batch_analyze(
            data=data,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    @mcp.tool(
        name="batch-analyze-sequences",
        description=BATCH_ANALYZE_SEQUENCES_DESCRIPTION,
        annotations=READ_ONLY_HTTP_TOOL,
        structured_output=True,
    )
    async def batch_analyze_sequences(
        data: list[dict[str, Any]],
        timeout: int = 600,
        poll_interval: int = 2,
    ) -> dict[str, Any]:
        return await client.batch_analyze_sequences(
            data=data,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    @mcp.tool(
        name="analyze-structure",
        description=ANALYZE_STRUCTURE_DESCRIPTION,
        annotations=READ_ONLY_HTTP_TOOL,
        structured_output=True,
    )
    async def analyze_structure(
        pdb_file_path: str,
        rxn_smiles: str | None = None,
        timeout: int = 600,
        poll_interval: int = 2,
        slim: bool = True,
    ) -> dict[str, Any]:
        return await client.analyze_structure(
            pdb_file_path=pdb_file_path,
            rxn_smiles=rxn_smiles,
            timeout=timeout,
            poll_interval=poll_interval,
            slim=slim,
        )

    @mcp.tool(
        name="get-job-result",
        description=GET_JOB_RESULT_DESCRIPTION,
        annotations=READ_ONLY_HTTP_TOOL,
        structured_output=True,
    )
    async def get_job_result(job_id: str, slim: bool = True) -> dict[str, Any]:
        return await client.get_prediction_result(job_id=job_id, slim=slim)

    return mcp, client


def run_server(settings: EasifaMCPSettings) -> None:
    mcp, client = create_server(settings)
    try:
        mcp.run(transport="stdio")
    finally:
        asyncio.run(client.aclose())
