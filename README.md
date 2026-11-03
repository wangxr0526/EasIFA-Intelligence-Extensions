# EasIFA Intelligence Extensions

`EasIFA-Intelligence-Extensions` is the official companion repository for EasIFA 2.0 webserver described at [cadd.drugflow.com/easifa/description](https://cadd.drugflow.com/easifa/description).

As described on the EasIFA website, the EasIFA 2.0 platform focuses on scalable, high-throughput enzyme active-site prediction with high-performance APIs, intelligent caching, agent-based task coordination, and AI-agent integration. This repository is the official integration layer that extends those EasIFA 2.0 capabilities into MCP-capable LLM clients.

This is not a third-party add-on. It is the officially supported way to embed EasIFA 2.0 into agentic systems and production AI workflows, so users can bring EasIFA-powered enzyme analysis into virtually any Agent environment that supports MCP, local instructions, or both.

In practice, the website and this repository are designed to work together:

- the EasIFA website is the user-facing product for browser-based submission, result visualization, database access, API exploration, and agent pages
- `easifa-web-extensions` is the official bridge that lets Claude, Codex, Copilot, and other MCP clients call EasIFA from an LLM workflow
- the bundled skill gives agents the official usage guidance needed to choose EasIFA tools correctly and present EasIFA results in a readable, link-preserving way

Use the EasIFA website when you want an interactive web experience. Use this repository when you want to embed EasIFA 2.0 into your own Agent workflow for tasks such as searching UniProt candidates, inspecting annotated sites, submitting structures or sequences, running batch jobs, and fetching EasIFA results without leaving the agent environment.

It currently ships three things:

- `easifa_mcp/`: a lightweight local MCP server that connects MCP clients to EasIFA over `stdio`
- `skills/easifa-mcp-usage/`: an agent skill focused on using EasIFA MCP well after it has been connected
- `.claude/`, `.codex/`, `.copilot/`, `.vscode/`: ready-to-adapt client configuration templates for Claude, Codex, and Copilot

The MCP server does not load EasIFA model weights and does not run inference locally. It acts as a thin bridge between MCP clients and an existing EasIFA deployment, so the same setup can target the public service or your own environment.

The MCP server and the skill are designed to be used together:

- `easifa_mcp` gives your client the actual EasIFA tools
- `easifa-mcp-usage` teaches the agent how to choose those tools and present EasIFA results well

If your client supports both MCP and skills, install both for the best experience.

## What You Can Do With It

The current MCP server exposes eight tools. The original six keep their existing parameters:

| Tool | Purpose |
| --- | --- |
| `query-uniprot` | Find candidate UniProt entries by enzyme name |
| `query-uniprot-sites` | Retrieve catalytic or binding-site annotations for a UniProt accession |
| `batch-analyze` | Run batch analysis from UniProt accessions |
| `batch-analyze-sequences` | Run batch analysis from amino-acid sequences |
| `analyze-structure` | Upload a local `.pdb` file and poll until prediction finishes |
| `get-job-result` | Fetch the latest EasIFA result payload for a job ID |
| `create-job-share-link` | Explicitly create a read-only browser link for one owned task |
| `revoke-job-share-link` | Revoke a task's current share link and sharing sessions |

## Quick Start

Requirements:

- Python 3.10+
- `uv`
- Access to an EasIFA deployment

Install the project dependencies and start the MCP server:

```bash
git clone https://github.com/wangxr0526/EasIFA-Intelligence-Extensions.git easifa-web-extensions
cd easifa-web-extensions
uv sync
uv run easifa-mcp \
  --base-url https://cadd.drugflow.com/easifa \
  --backend-base-url https://cadd.drugflow.com/easifa
```

You can also configure the server through environment variables:

```bash
export EASIFA_AGENT_BASE_URL=https://cadd.drugflow.com/easifa
export EASIFA_BACKEND_BASE_URL=https://cadd.drugflow.com/easifa
uv run easifa-mcp
```

Public EasIFA base URLs currently available for both `EASIFA_AGENT_BASE_URL` and `EASIFA_BACKEND_BASE_URL`:

- `https://cadd.drugflow.com/easifa`
- `https://cadd.zju.edu.cn/easifa`
- `http://cadd.iddd.group/easifa`

## Recommended Configuration

Core variables:

- `EASIFA_AGENT_BASE_URL`: primary EasIFA base URL used by the MCP server
- `EASIFA_BACKEND_BASE_URL`: EasIFA base URL used for structure submission and result retrieval
- `EASIFA_AGENT_BEARER_TOKEN`: optional bearer token for protected deployments
- `EASIFA_AGENT_TIMEOUT_SECONDS`: HTTP timeout, default `120`
- `EASIFA_SESSION_KEY`: optional persistent anonymous owner key; takes priority over the saved file
- `EASIFA_MCP_SESSION_FILE`: optional absolute path to a persistent owner recovery file

Optional public URL rewriting variables:

- `EASIFA_PUBLIC_WEB_BASE_URL`: user-facing web URL used in returned submission and result links
- `EASIFA_PUBLIC_AGENT_BASE_URL`: user-facing agent URL used in returned polling links
- `EASIFA_PUBLIC_API_BASE_URLS`: comma-separated public API base URLs used for fallback resolution

For a single public EasIFA deployment:

```bash
export EASIFA_AGENT_BASE_URL=https://cadd.drugflow.com/easifa
export EASIFA_BACKEND_BASE_URL=https://cadd.drugflow.com/easifa
export EASIFA_PUBLIC_WEB_BASE_URL=https://cadd.drugflow.com/easifa
export EASIFA_PUBLIC_AGENT_BASE_URL=https://cadd.drugflow.com/easifa/agent
uv run easifa-mcp
```

## Private Jobs And Recovery

Gateway submissions, structure submissions, result reads, and configured fallback endpoints all send the same `X-Easifa-Session` header. The tool arguments and API submission bodies are unchanged. The Gateway bearer token still authenticates the service; it does not replace the task owner's key.

Without `EASIFA_SESSION_KEY`, the MCP creates a small recovery file at `$XDG_STATE_HOME/easifa-mcp/<profile>/session.json` (default state directory: `~/.local/state`). The profile is derived from the configured backend addresses. Restarting with the same configuration reuses this identity. The file is created atomically with permissions `0600` on POSIX. An unreadable or invalid existing file stops startup instead of silently changing owners.

For a stable location across endpoint changes, containers, or multiple clients belonging to the same person, configure `EASIFA_MCP_SESSION_FILE` to a private persistent path. Keep this file when upgrading or reinstalling. Each independent user must use a separate file or key. Changing the file/key creates a different owner and does not transfer previous tasks.

The file uses the website's `easifa-access` recovery format. Import it through the website's **Restore access** control to access the same jobs in your browser, or point MCP at a recovery file exported from that browser (set permissions to `0600`). If using `EASIFA_SESSION_KEY`, restore that key in the browser instead. The owner credential grants access to all tasks belonging to that identity: never put it in a result URL, chat response, or source control.

For a link that works in a separate browser without importing the owner identity, explicitly call `create-job-share-link(job_id=...)`. Its `share_url` grants read access to only that task. It leaves the task private unless it was already public, and replaces any earlier share link for that task. `revoke-job-share-link` invalidates the link and already-redeemed sharing cookies; public tasks remain publicly accessible. These two tools require the server's job-privacy upgrade. Ordinary result reads do not create or rotate share links.

Existing private jobs created before this client fix still require their original owner key or recovery file. A newly generated identity cannot recover a lost credential. Historical Legacy Public tasks remain readable as before.

## Connect EasIFA MCP To Your Client

This repository already includes checked-in client templates. Treat them as examples and replace the local repository path with the path of your own clone.

The common `stdio` command is:

```bash
uv run --directory /ABS/PATH/TO/easifa-web-extensions easifa-mcp
```

### Claude

Use the Claude CLI:

```bash
claude mcp add --transport stdio --scope user easifa \
  --env EASIFA_AGENT_BASE_URL=https://cadd.drugflow.com/easifa \
  --env EASIFA_BACKEND_BASE_URL=https://cadd.drugflow.com/easifa \
  -- uv run --directory /ABS/PATH/TO/easifa-web-extensions easifa-mcp
```

Repository template:

- `.claude/settings.local.json`

### Codex

Use the Codex CLI:

```bash
codex mcp add easifa \
  --env EASIFA_AGENT_BASE_URL=https://cadd.drugflow.com/easifa \
  --env EASIFA_BACKEND_BASE_URL=https://cadd.drugflow.com/easifa \
  -- uv run --directory /ABS/PATH/TO/easifa-web-extensions easifa-mcp
```

Repository template:

- `.codex/config.toml`

### Copilot

For GitHub Copilot in VS Code, adapt the checked-in workspace template:

- `.vscode/mcp.json`

For GitHub Copilot CLI, adapt:

- `.copilot/mcp-config.json`

In both cases, keep the same `uv run --directory ... easifa-mcp` command and update the repository path plus any EasIFA environment variables you need.

## Included Skill

`skills/easifa-mcp-usage/` is an English skill for agents that already have EasIFA MCP connected. It is intentionally focused on MCP usage rather than installation:

- when to choose each EasIFA tool
- how to structure EasIFA inputs
- how to present EasIFA outputs as readable markdown tables
- how to preserve result links such as `submission_endpoint`, `result_endpoint`, `poll_url`, and `result_url`

This skill is meant to accompany the MCP server, not replace it:

- install the MCP server so the client can call EasIFA tools
- install the skill so the agent knows how to use those tools effectively

### Install The Skill

From the repository root, copy the `skills/easifa-mcp-usage` folder into your client's local skills directory.

For Codex:

```bash
mkdir -p ~/.codex/skills
cp -R skills/easifa-mcp-usage ~/.codex/skills/
```

Then restart Codex so it can load the new skill.

For Claude:

```bash
mkdir -p ~/.claude/skills
cp -R skills/easifa-mcp-usage ~/.claude/skills/
```

If you prefer a project-local install, you can place it under `.claude/skills/easifa-mcp-usage` in your working repository instead.

Then restart Claude or Claude Code so it can load the new skill.

For Copilot:

- the MCP server templates in this repository are directly usable
- Copilot does not use this repository's skill folder in the same way as Codex or Claude, so the paired setup for Copilot is the MCP server plus your usual Copilot instructions/customization flow

## Validate Your Setup

Run the tests:

```bash
uv run --extra dev pytest
```

For a quick manual smoke test, verify that:

1. `uv run easifa-mcp` starts without errors.
2. Your MCP client can see all eight tools.
3. `query-uniprot` returns candidate records.
4. `analyze-structure` can upload a local `.pdb` file and later resolve a result.
5. After restarting MCP, `get-job-result` can read the same private job.
6. An explicitly created share link opens in a separate browser and stops granting access after revocation.
