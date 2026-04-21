---
name: easifa-mcp-usage
description: Use when operating EasIFA through the EasIFA MCP server, including query-uniprot, query-uniprot-sites, batch-analyze, batch-analyze-sequences, analyze-structure, and get-job-result, and when presenting EasIFA responses as concise markdown tables with result links when available.
---

# EasIFA MCP Usage

Use this skill after EasIFA MCP is already connected. Focus on choosing the right tool, shaping inputs correctly, interpreting the response, and presenting the output in a clean user-facing format.

## When To Use

- When the user wants UniProt candidates for an enzyme name
- When the user wants catalytic-site or binding-site annotations for a UniProt accession
- When the user wants batch analysis from UniProt IDs
- When the user wants batch analysis from amino-acid sequences
- When the user has a local `.pdb` file and wants EasIFA to analyze it
- When the user already has a `job_id` and wants the latest EasIFA result payload

## Tool Selection Guide

| Tool | Use it when | Typical input |
| --- | --- | --- |
| `query-uniprot` | The user starts from an enzyme name and needs candidate UniProt entries | `enzyme_name`, optional `size` |
| `query-uniprot-sites` | The user already knows the UniProt accession and wants site annotations | `uniprot_id` |
| `batch-analyze` | The user wants EasIFA runs for one or more UniProt accessions | `data=[{"uniprot_id": "..."}]` |
| `batch-analyze-sequences` | The user wants EasIFA runs from amino-acid sequences | `data=[{"aa_sequence": "...", "rxn_smiles": "matching reaction"}]` |
| `analyze-structure` | The user has a local PDB structure file to upload | `pdb_file_path`, optional `rxn_smiles` |
| `get-job-result` | The user wants to re-check a known EasIFA job | `job_id` |

If `rxn_smiles` is provided for `batch-analyze-sequences`, it should describe the reaction catalyzed by the corresponding `aa_sequence` in the same item.

## Response Handling Rules

- Lead with the conclusion, then show the structured output.
- Prefer markdown tables instead of dumping raw JSON.
- Preserve result links whenever the payload provides them.
- If the payload contains `submission_endpoint`, `result_endpoint`, `poll_url`, or `result_url`, surface them in dedicated columns instead of hiding them in prose.
- If a job is still `pending`, `queued`, or `processing`, say that clearly and show the polling route.
- If the user asks for raw fields, provide them after the table rather than instead of the table.

## Suggested Table Shapes

### `query-uniprot`

| UniProt ID | Protein | Organism | EC | Reviewed | Link |
| --- | --- | --- | --- | --- | --- |

Use `N/A` when a field is absent.

### `query-uniprot-sites`

| UniProt ID | Site Type | Residue | Position | Evidence | Link |
| --- | --- | --- | --- | --- | --- |

Expand multiple sites into one row per site when possible.

### `batch-analyze` and `batch-analyze-sequences`

Start with job-level status:

| Job ID | Status | Poll Link | Result Link |
| --- | --- | --- | --- |

If item-level results are already available, add a second table:

| Input | Status | Top Prediction | Score | Result Link |
| --- | --- | --- | --- | --- |

### `analyze-structure` and `get-job-result`

Start with the job summary:

| Job ID | Status | Submission Page | Result Page |
| --- | --- | --- | --- |

If prediction details are available, follow with a compact residue table:

| Chain | Residue Index | Residue | Probability / Score | Site Type |
| --- | --- | --- | --- | --- |

## Output Style

- Keep the first paragraph short and decision-oriented.
- Keep result links visible and clickable when they exist.
- If there are many rows, show the most relevant rows first and say that the remainder was omitted.
- Avoid repeating large JSON payloads unless the user explicitly asks for the raw response.
