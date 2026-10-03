# Testing

## Required commands

## Sprint 8 coverage

- smoke Dataset 被 Quality Gate 拒绝且不创建模型。
- Label Cohort 少于 5 个完整候选时不创建 Training Sample。
- 70/15/15 时间切分的三段均要求同时包含正负 Label。
- Logistic Regression、Random Forest、XGBoost 均执行 fit/evaluate，保存完整指标和 Feature Importance。
- 模型训练后不自动 ACTIVE；低于门槛的显式激活被拒绝。
- 无 ACTIVE 模型时 Forecast API/UI 显示 NOT_READY 并回退 Potential Score。
- Data Leakage Guard 与 Feature provenance 回归测试持续执行。

Backend, from `backend/`:

```bash
pytest
ruff check .
python manage.py check
```

Frontend, from `frontend/`:

```bash
npm run lint
npm run type-check
npm run test
npm run build
```

Repository convenience command:

```bash
make test
```

Sprint 1 backend tests cover GitHubClient request/error behavior, deterministic classification,
Repository create/update idempotency, manual category preservation, Topic replacement and database
uniqueness, Discovery Query Pool use, and fork/archive filtering. They use `FakeGitHubClient`; no
routine test consumes live GitHub rate limits.

Migration verification:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate
```

Sprint 2 adds tests for:

- deterministic six-hour UTC bucket calculation
- ten repeated same-bucket UPSERTs producing one row
- NULL preservation and completeness
- database uniqueness as the second duplicate defense
- commit-only follow-up callback
- Redis TTL lock exclusion and token-safe release
- Celery retry on lock contention
- Beat dispatcher filtering and queue configuration

Compose integration also verifies PostgreSQL constraints, ten real PostgreSQL UPSERTs, real Redis
two-contender exclusion, Worker task registration/queue consumption and Beat startup.

Sprint 4 adds tests for:

- age-cohort boundary values and category+age isolation
- tie-aware, order-independent percentile ranks and NULL exclusion
- NULL versus zero and extreme-value clamping
- insufficient Snapshot history and completeness reduction
- deterministic Momentum, Development, Community, Delivery, Adoption and Maintenance composition
- Hype Risk completeness gate and lifecycle rule ordering
- algorithm-versioned UPSERT and repeat-calculation determinism
- committed Snapshot/Activity scoring dispatch and `scoring` queue routing

Compose integration verifies the Trend migration and constraints, production-service PostgreSQL
UPSERT, evidence persistence, Worker task registration, Redis and both Health paths.

Sprint 5 adds backend API tests for Dashboard aggregation, persisted Trend projection, Discover
filter/sort/pagination validation, explicit future-score rejection, NULL preservation, metrics range,
404 behavior, Trend Evidence and insufficient-history status. Frontend tests cover the typed API
transport, Dashboard, Discover, Repository Detail, NULL-versus-zero rendering and Score Evidence.

Sprint 5 Compose verification must use `docker compose config --quiet`; verbose resolved Compose
configuration is forbidden because it can print interpolated secrets. Runtime smoke covers all six
services, Backend and proxied Health, Dashboard/Project APIs, PostgreSQL, Redis and Celery.

Sprint 6 adds tests for deterministic Potential arithmetic, NULL versus zero, missing-Hype
confidence reduction, known-Hype penalty, extreme/clamped values, multi-signal candidate rules,
small-project momentum isolation, versioned UPSERT, confidence database constraint, Celery routing,
Trend-to-Potential dispatch, ranking order, Potential filters/API/Evidence and frontend explanation.
Compose integration applies the Potential migration, verifies both database constraints, executes
the task twice through a real Redis/Celery Worker, confirms one row, and smokes all Potential API/UI
paths. Compose configuration remains `docker compose config --quiet` only.

Sprint 7 adds tests for three-window Historical Backfill, BACKFILLED provenance, Search incomplete
NULL handling, real zero preservation, label-window maturity, label-v1.1 Category percentiles,
Feature/Label versions, multiple sample points, UPSERT idempotency, incomplete-label exclusion,
database constraints, quality statistics and explicit Data Leakage rejection of future Feature
timestamps/repository_id. GitHubClient also tests truncated HTTP response wrapping.

Compose integration applies Dataset migration/constraints, registers both dataset tasks on
`github_backfill`, and performs a real public-repository backfill. The first Contributor Statistics
202 produces no partial write; retry writes three BACKFILLED windows. Building twice returns
created=1 then updated=1, one versioned sample, complete quality JSON and zero fabricated Snapshot.

## Sprint 8.5 coverage

- deterministic Tier rules, centralized intervals and next Snapshot times
- Discovery GitHub-ID deduplication, Candidate-only membership and after-commit first Snapshot
- bounded hourly due dispatcher, archive/disabled filtering and Core budget pause
- Snapshot observation fields, NULL preservation and same-bucket UPSERT idempotency
- bounded real Discovery and three-repository NEW/NORMAL/STABLE dispatcher smoke
- PostgreSQL migration, Redis, Celery Worker/Beat and both Health paths
- repository-disjoint XGBoost holdout with zero Repository overlap

## Sprint 9 coverage

- heading-aware Markdown chunking preserves headings/code/list/table blocks
- Document identity, content-hash skip, version increment and chunk rebuild idempotency
- real vector generation with model/version and repository-filtered retrieval
- deterministic PR/Issue selection evidence and bounded source policy
- PostgreSQL vector Extension, cosine query, Redis lock and Celery knowledge queue
- real README/Docs/Release plus selected PR/Issue ingestion and traceable Evidence smoke

## Sprint 10 coverage

- Learning/Enterprise 权重、边界、NULL/0、确定性与版本化 UPSERT
- Knowledge `NOT_INGESTED` / `DOCUMENT_NOT_FOUND`、历史不足 Evidence 状态
- Hype penalty、archived maintenance=0 与 recommendation 边界
- Detail API、Discover 过滤/排序、confidence ranking gate 与低置信度 UI
- 真实 PostgreSQL Migration、20+ 分层仓库和 Knowledge Pilot 评分、API 与 Compose smoke
- V1.1 无 RAG 评分、轻量白名单 GitHub enrichment、最多三次 Contents 请求
- 全量分批 Dispatcher 续跑、Redis Lock、版本化 UPSERT 与重复 Celery 幂等
- Score 存在但低 confidence 的“数据积累中”展示，以及正式排名 confidence gate

## Sprint 11 coverage

- 13-tool Registry discovery, schemas, bounds, unknown tool and structured errors
- four composed Tool scenarios, NULL/status preservation and no domain-row mutation
- MCP initialize/tools-list/tools-call contract and real stdio subprocess startup
- real PostgreSQL structured Tool calls and pgvector Knowledge retrieval
- per-call duration, DB query count, timeout and result-byte metadata
- Forecast remains `NOT_READY`; no VALIDATED model is executed

## Sprint 12 coverage

- six Markdown/JSON Skill contracts, semantic versions and one-to-one Intent mapping
- Registry list/get/resolve, unknown/disabled Skill and invalid Tool reference rejection
- Dry Run performs no Tool calls; workflow order and Tool whitelist validation
- budget exhaustion, partial failure, minimum Evidence, confidence fallback and NULL preservation
- six real deterministic workflows through ToolRegistry to PostgreSQL/pgvector
- Forecast `NOT_READY → CURRENT_SIGNAL_ANALYSIS` without probability or model inference
- before/after protected production row counts remain identical

## Sprint 14 coverage

覆盖关注添加/重复/取消、只读无副作用、Alert 历史门禁与数据库去重、Potential confidence、
Release/Dormant Evidence、日报周报时间桶幂等、API、16个 Tool/9个 Skill、Vue loading/error/empty
状态。真实验收必须通过 PostgreSQL、Redis、Worker/Beat、双 Health 与真实 Celery task。

## Sprint 15 production gates

CI 依次执行 Backend pytest、Ruff、Django check、Migration drift、Frontend lint/type-check/Vitest/build，
随后 Compose 以显式 Migration 启动并检查 PostgreSQL、Redis、Celery 与双 Health。生产验收另执行
`scripts/production_smoke.sh`，其凭据随机生成且输出固定脱敏；备份恢复使用 `scripts/verify_restore.sh`
对隔离数据库核对关键表 count。

## V1 PM Copilot intent coverage enhancement

- 13个Intent与13个版本化Skill严格一一映射，17个MCP Tool仍全部只读
- 全局/分类趋势前20、高潜前10、普通发现、项目知识和可信系统说明路径
- Learning/Enterprise分类可选，搜索列表与前三项深入Evidence预算分离
- `user_goal`、`risk_preference`、`knowledge_query`等上下文只能进入声明它们的步骤
- 切换Intent后旧Category不串入新问题；同Intent连续追问仍可继承约束
- 项目知识仍执行不可信内容清理，Potential不描述为Forecast概率，NULL不转0
