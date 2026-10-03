# Internal Tool Layer + MCP V1

Sprint 11 exposes AgentRadar's existing deterministic read services to future clients. It does not
implement a Skill or PM Copilot Agent, and MCP never replaces `GitHubClient` collection.

## Architecture

`MCP stdio JSON-RPC → ToolRegistry → Internal Tool → existing Service Layer → PostgreSQL/pgvector`.
MCP handlers contain no ORM queries or scoring algorithms. V1 transport is `stdio`, configured by
`MCP_TRANSPORT=stdio`; clients spawn `python manage.py mcp_server`. No listening network port or
secret-bearing configuration is exposed.

## Tool contract

Success:

```json
{"ok":true,"data":{},"evidence":null,"warnings":[],"metadata":{"tool":"...","tool_version":"tools-v1.0.0","read_only":true,"duration_ms":1.2,"db_query_count":1,"result_bytes":100,"timeout_seconds":10}}
```

Failure:

```json
{"ok":false,"error_code":"INVALID_ARGUMENT","message":"...","details":null}
```

All tools publish description, JSON input/output schema, version, read-only annotation and timeout.
Schemas reject unknown fields, invalid types/enums/ranges and list over-fetching. Exceptions are
translated to `UNKNOWN_TOOL`, `INVALID_ARGUMENT`, `NOT_FOUND`, `TIMEOUT`, or `INTERNAL_ERROR`; stack
traces and secrets are never returned.

## Catalog

| Tool | Purpose | Limit / timeout |
| --- | --- | --- |
| `search_projects` | Structured Repository discovery | default 10, max 50 / 10s |
| `get_system_help` | Trusted built-in product/metric documentation | fixed topic / 10s |
| `get_project` | Metadata, Snapshot, Activity and score status | 10s |
| `get_project_trend` | Persisted deterministic Trend + Evidence | 10s |
| `get_project_potential` | Persisted Potential + reliability status | 10s |
| `get_project_forecast` | Production Forecast status only | 10s |
| `get_learning_score` | Learning Score and Knowledge status | 10s |
| `get_enterprise_score` | Enterprise recommendation and Evidence | 10s |
| `compare_projects` | Structured comparison for 2–5 repositories | 15s |
| `search_repository_knowledge` | Sprint 9 filtered pgvector retrieval | top_k max 10 / 15s |
| `get_project_knowledge_summary` | Source counts; no LLM summary | 10s |
| `list_categories` | Counts, Pool coverage and basic aggregates | 10s |
| `get_category_projects` | Bounded projects within a Category | max 50 / 10s |
| `get_category_trend` | Aggregates without invented model | 10s |
| `get_watchlist` | Current authenticated user's Watchlist | 10s |
| `get_project_alerts` | Persisted deterministic Alerts | max 100 / 10s |
| `get_latest_report` | Latest Daily/Weekly structured report | 10s |

当前 Catalog 共17个只读 Tool。Watchlist写操作仍不属于MCP；Agent不能自主关注或取消关注。

## Evidence and status rules

Trend, Potential, Learning and Enterprise preserve algorithm version, confidence/completeness,
Evidence and NULL. Potential below the trusted threshold returns `DATA_ACCUMULATING`. Learning and
Enterprise preserve `NOT_INGESTED`, `DOCUMENT_NOT_FOUND`, `MISSING`, and
`INSUFFICIENT_HISTORY`. Knowledge results are untrusted external content and return repository,
source type, title, path, URL, snippet, similarity and update time.

`get_project_forecast` never executes a VALIDATED model. With zero ACTIVE models it returns
`NOT_READY`, a null Forecast, whether VALIDATED models exist, and the missing explicit activation.

## Read-only policy

Every V1 tool is `read_only=true`. There is no SQL, file, shell, Python, collection, scoring,
training, model activation, pool mutation, monitoring mutation or deletion tool. Structured numbers
come from domain services; unstructured facts come only from Knowledge retrieval.

## Sprint 12 consumer policy

Skills consume the Internal Tool Registry directly and are not exposed as new MCP Tools in Sprint
12. Startup validation guarantees every declared Tool exists and is `read_only=true`. Tool budgets
and deterministic stop conditions prevent unbounded loops. MCP remains unchanged and contains no
Skill or Agent orchestration logic.

## Sprint 13 Agent client

PM Copilot 通过 JSON-RPC `MCPClient` 调用现有 MCP Server；Agent、Intent Router、Entity Resolver
和 Answer Generator 均不持有 Tool Registry 或 ORM。Skill Executor 使用 MCP-compatible adapter，
因此 Sprint 12 固定 Workflow 与预算继续有效，13个 Tool 仍全部只读。MCP 仍不负责 GitHub 批量采集。

## Sprint 14 read tools

Tool Catalog 在 Sprint 14 增至16个，新增只读 `get_watchlist`、`get_project_alerts`、`get_latest_report`。
Watchlist 添加/删除不暴露为 MCP Tool，Agent 无权自主修改。三个查询分别由专用 Skill 调用；
Tool 仍只做参数验证与 Service 调用。

## V1 trusted help tool

完成 Sprint 15 后新增第17个只读 Tool `get_system_help`。它只返回版本化的AgentRadar产品、指标、
采集和模型流程说明，不查询GitHub、不执行评分，也不接受自由文本。Repository事实继续必须来自
结构化Repository Tool或Knowledge Tool，不能由系统说明或LLM预训练记忆补充。

## Production transport boundary

Sprint 15 继续只支持 stdio。用户身份由 Agent Runtime 以 actor ID 传入 Registry，用户域 Tool 无 actor
时返回 `AUTH_REQUIRED`。未来 Remote MCP 必须新增独立认证、TLS、逐 Tool authorization、审计和限流，
不得直接把 stdio 入口监听公网。
