# Confluence MCP Knowledge Assistant

A small, interview-ready Python chatbot that lets an OpenAI model discover and
call read-only MCP tools, retrieves engineering documentation, and produces a
bounded, source-grounded answer. Demo mode is fully local except for the OpenAI
answering call; evaluation is deterministic and makes no paid LLM calls.

The repository contains fictional documentation only. It includes no Panasonic
code, data, URLs, or credentials.

## Architecture

```text
User (terminal)
      |
      v
app.py -- OpenAI Responses tool loop -- max 4 rounds / 8 calls
      |                                  |
      | MCP tool schemas                 | function calls
      v                                  v
mcp_client.py ===================== MCP server
      |                              /         \
      | demo: stdio                 /           \ remote: Streamable HTTP
      v                            v             v
demo_server.py -> documents.json          Atlassian Rovo MCP
      |
      v
retrieval.py -> dedupe -> max 5 pages -> bounded evidence -> grounded answer
```

The model chooses when and how to call the MCP search/read tools. The application
enforces read-only tool filtering, call limits, page limits, deduplication, and a
total evidence budget. The final answer is generated in a separate no-tools call
using only the full pages that were actually retrieved.

## Setup

Python 3.11 or newer is required. The project is tested with Python 3.13.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. The default, `gpt-6-luna`, is the current
cost-focused model recommended by the official [OpenAI model guide](https://developers.openai.com/api/docs/models).
It is configurable through `OPENAI_MODEL`; use a model available to your OpenAI
project that supports Responses API function calling.

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Then add `OPENAI_API_KEY` to `.env`.

## Run the demo chatbot

The default `.env.example` already selects demo mode. The client launches
`demo_server.py` as an MCP stdio subprocess; it never reads `documents.json`
directly.

```powershell
python app.py
```

Example questions:

```text
How does our CI pipeline report failed tests?
How long are those artifacts retained?
What happens when a deployment breaches an SLO?
What is our cafeteria menu?  # should report insufficient documentation
```

Each answer prints measured end-to-end response time, MCP call count, and full
page count. Times depend on the network and selected model and are not claimed as
benchmark results.

## Evaluation and tests

Retrieval evaluation runs 30 questions through the actual local MCP server and
reports Hit@3, Recall@3, mean search latency, p95 search latency, source
attribution, and insufficient-context checks. It does not use OpenAI.

```powershell
python eval.py
pytest -q
```

GitHub Actions runs the test suite and deterministic retrieval evaluation on
pushes, pull requests, and manual dispatches. These checks do not require an
OpenAI API key.

The lexical demo search is intentionally simple and deterministic. In real mode,
Confluence performs discovery; no vector database or local embedding index is
used.

## Real Atlassian Confluence mode

The remote adapter uses MCP Streamable HTTP and forwards one configured
`Authorization` header. It exposes only tool names that look read-only
(`search`, `get`, `list`, `discover`, or `executeRead`) unless
`MCP_ALLOWED_TOOLS` is explicitly set.

Current Atlassian setup:

1. Ask an organization admin to enable the Atlassian Rovo MCP server and the
   read/search Confluence permission groups.
2. Connect to `https://mcp.atlassian.com/v2/mcp`. If a client requires the full
   paginated tool list, use `https://mcp.atlassian.com/v2/mcp?tools=all`.
3. Prefer OAuth 2.1 for an interactive user application. This sample deliberately
   does not implement a custom OAuth flow. Supply a valid access token as a
   Bearer header, or use API-token authentication only if the organization admin
   has enabled it.
4. Grant only `read:confluence:agent-interface` and
   `search:confluence:agent-interface`; do not grant write/delete scopes for this
   assistant.
5. If personal API tokens are enabled, Atlassian expects Basic auth containing
   base64-encoded `email:api_token`. Service-account API keys use Bearer auth.

Configure `.env` without committing it:

```dotenv
MCP_MODE=remote
MCP_REMOTE_URL=https://mcp.atlassian.com/v2/mcp
MCP_AUTH_HEADER=Bearer your-token-or-service-account-key
# Optional hard allowlist after inspecting the tools available to your account:
MCP_ALLOWED_TOOLS=searchConfluence,getConfluenceContent,discover,executeRead
```

Tool availability and response shapes depend on Atlassian authentication,
organization policy, product access, scopes, and server version. Demo mode and
the generic remote MCP transport are tested; a live Atlassian tenant is not.
Consult the official [Atlassian Rovo MCP getting-started guide](https://developer.atlassian.com/cloud/rovo-mcp/guides/getting-started/),
[supported tools](https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/),
and [API-token authentication guide](https://developer.atlassian.com/cloud/rovo-mcp/guides/configuring-authentication-via-api-token/)
for current tenant configuration.

## Files to explain in an interview

- `app.py`: CLI, limited history, OpenAI tool loop, and final grounded answer.
- `mcp_client.py`: one reusable adapter for stdio and Streamable HTTP.
- `demo_server.py`: MCP 2.x server plus transparent lexical search.
- `retrieval.py`: evidence extraction, deduplication, limits, and checks.
- `eval.py`: deterministic retrieval/latency evaluation through MCP.
- `documents.json` / `eval_questions.json`: 15 fictional pages and 30 queries.

## Deliberate limitations

- A valid OpenAI API key is required for chatbot answers; retrieval evaluation
  and tests need no key.
- Follow-up memory is limited to the last three user/assistant turns and is not
  persisted.
- Remote OAuth token acquisition/refresh is delegated to the environment or an
  external credential manager.
- Real Atlassian result shapes can evolve. The collector recognizes common page
  fields; validate citation extraction against the tools enabled in your tenant.
- There is no reranker, embedding store, UI, web service, Docker image, or cloud
  deployment by design.
