# agentGitHub Architecture

## Sprint 7 historical dataset application

AgentRadar is a modular monolith. The repository contains a Django/DRF backend, Vue 3 frontend, PostgreSQL with pgvector, Redis, Celery worker/beat, and Docker Compose orchestration.

Sprint 1 adds the Repository domain and GitHub ingestion boundary. Sprint 2 adds Snapshot; Sprint 3
adds Activity collection. Sprint 4 adds a deterministic Trend Engine over persisted Repository,
Snapshot and Activity data. Sprint 5 adds a database-backed read service, DRF Dashboard/Project
API and Vue pages. Sprint 6 adds a deterministic Potential Engine over persisted Sprint 4 Trend
results. Sprint 7 adds provenance-aware historical activity windows and deterministic Dataset
Builder. Model training, Forecast, RAG, MCP, Skill runtime and Agent remain unimplemented.

```text
Vue -> Django/DRF -> PostgreSQL
          |
          +-> Celery -> Redis

GitHub REST -> RealGitHubClient -> RepositoryDiscoveryService / RepositoryService -> PostgreSQL
Tests       -> FakeGitHubClient -> RepositoryDiscoveryService / RepositoryService -> test database

Celery Beat -> Snapshot dispatcher -> github_normal queue -> Repository Snapshot Task
Repository Snapshot Task -> Redis Lock -> GitHubClient -> DB Transaction -> on_commit hook
Snapshot/Activity commit -> scoring queue -> TrendService -> repository_trend_scores UPSERT
Trend persisted -> scoring queue -> PotentialService -> repository_potential_scores UPSERT
Vue Dashboard/Discover/Detail -> /api/v1 -> RepositoryReadService -> persisted domain data
Admin/Task -> github_backfill queue -> GitHubClient -> BACKFILLED activity windows
Activity windows -> Leakage Guard -> Feature/Label Builder -> versioned training_samples
```

## Boundaries

## Sprint 8 forecast pipeline

`TrainingSample → DatasetQualityGate → Time-based Split → Logistic/RandomForest/XGBoost →
Evaluation → Model Registry (VALIDATED) → explicit activation → ForecastService`。

质量门禁失败时在训练前终止，不生成 artifact 或 Registry 行。API 只读取 Registry/Forecast 数据；
无 ACTIVE 模型时返回 Potential Score fallback。训练与推理任务使用 `ml` Celery queue。

- `backend/config`: Django and Celery runtime configuration.
- `backend/apps/common`: cross-cutting infrastructure only; currently a health endpoint.
- `backend/apps/github`: GitHubClient protocol, real REST adapter, errors and deterministic fake.
- `backend/apps/repositories`: Repository/Topic/Query models, classifier, services, admin and commands.
- `backend/apps/snapshots`: Snapshot model, bucket/service, Redis lock, Celery tasks and tests.
- `backend/apps/activities`: daily GitHub activity metrics, contributors and releases.
- `backend/apps/trends`: pure scoring functions, cohort/percentile feature service, score model and
  Celery tasks. This module never calls GitHub or an LLM.
- `backend/apps/potentials`: pure Potential formula/candidate rules, versioned persistence and
  scoring tasks. It consumes persisted Trend only and never calls GitHub, an LLM or an ML model.
- `backend/apps/datasets`: Historical Backfill, provenance, Feature/Label builders, leakage guard,
  versioned Training Sample persistence and quality reporting. It contains no model training.
- `frontend/src`: typed API client, Dashboard, Discover, Repository Detail, ECharts adapters and
  explicit NULL/evidence presentation.
- `docker-compose.yml`: local runtime topology.

GitHub HTTP is allowed only in `RealGitHubClient`. Repository persistence remains behind services.
The Compose worker consumes `celery`, `github_normal`, `github_backfill` and `scoring`. Trend dispatch occurs only
after Snapshot/Activity persistence succeeds. Trend V1 rules are documented in `TREND_ENGINE.md`.
The public read API never calls GitHub. Trend responses are projections of Sprint 4 persisted scores,
and the browser has no GitHub credential or direct GitHub transport.
Potential calculation is dispatched only after Trend persistence succeeds. Dashboard ranking reads
the versioned Potential row and exposes evidence rather than presenting it as a probability.
Backfilled GitHub activity never mutates OBSERVED Snapshot rows. Feature timestamps are audited at
or before sample_at; Label windows start strictly afterward. Forecast remains NOT_READY.

## Sprint 8.5 continuous monitoring

`Celery Beat → hourly due dispatcher → bounded github_normal tasks → Redis repository lock →
GitHubClient → transactional Snapshot UPSERT → tier/next time`。

Beat also schedules continuous Discovery every six hours and recent-push refresh daily. New GitHub
IDs pass metadata sync and deterministic classification, enter Candidate only, and receive their
first Snapshot after commit. Intervals are configured centrally; no per-repository Beat entries are
created. Star/Fork growth is derived only from elapsed OBSERVED rows and remains NULL until enough
history exists.

`monitoring-priority-v1.1.0`每日从PostgreSQL本地重评采集层级，不请求GitHub。Watchlist、OBSERVED
增长、Activity/Release、确定性评分、CONFIRMED Training覆盖和ACTIVE模型结果共同决定优先级；
模型信号仅能升频，不能让低预测项目失去最低采样。STABLE/DORMANT仍保留周期Snapshot，避免反馈循环。
真实OBSERVED Snapshot跨度不足60天的项目处于采样保护期，最低保持NORMAL，防止训练数据成熟前被降频。
满60天后仍需同时满足30天Star/Fork低增长、开发Activity低、无Release、无用户关注、非训练覆盖且
无高评分/模型信号，才进入STABLE或DORMANT；缺失值不能被当作低值。
采集频率与7天/30天模型特征对齐：Training Pool固定每日覆盖，HOT为6小时、RISING为12小时、
新项目仅前7天保持12小时，之后在60天成熟期内按每日采集；前端API与图表数据结构不变。

## Sprint 9 Knowledge/RAG pipeline

`Tracked Pool → Celery knowledge queue → GitHubClient → content hash Document UPSERT → heading-aware
Chunk → EmbeddingClient → pgvector → metadata-filtered Retrieval → traceable Evidence`。

Structured numeric facts remain outside RAG. Repository-scoped retrieval filters the repository
before vector similarity; category/source/time filters support bounded cross-project research. V1
uses a local deterministic embedding baseline and does not implement Agent, MCP or Skill layers.

## Sprint 10 deterministic assessment

`Persisted Repository/Trend/Activity/Knowledge metadata → LearningService / EnterpriseService →
versioned score UPSERT → confidence-gated API ranking → Vue Evidence`。

评分服务不调用 GitHub、Embedding Provider 或 LLM。Knowledge 尚未采集与已采集但文档不存在采用
不同状态；缺失和历史不足降低 confidence。Sprint 10 没有实现 MCP、Skill 或 Agent。

V1 全量评分采用
`Repository/Activity/Trend/Contributor/Release/License → Learning/Enterprise Service → versioned UPSERT`。
RAG 只补充解释，不是算分门禁。缺少文件 Metadata 时，可由 Celery 的 GitHub normal queue 经统一
`GitHubClient` 对根目录、`docs/`、`.github/` 做最多三次白名单列表读取，并持久化轻量 Evidence。
评分 Dispatcher 分批、可续跑；单仓库 Task 使用 Redis Lock、有限 Retry 和数据库版本唯一约束。

## Sprint 11 Tool/MCP boundary

`Future Client → MCP stdio adapter → ToolRegistry → read-only ToolDataService/existing Services →
PostgreSQL/pgvector`。Tool Registry owns discovery, schema validation, timeout and structured errors;
MCP adapter only maps JSON-RPC. There is no GitHub collection or duplicated scoring logic in MCP.
All V1 tools are read-only. Skill and PM Copilot Agent remain unimplemented.

## Sprint 12 Skill policy boundary

`Intent fixture → SkillRegistry → versioned SKILL.md policy → deterministic SkillExecutor →
read-only ToolRegistry`。Skill definitions contain workflow and Evidence policy only. They have no
ORM, GitHub, model, embedding, scoring or LLM access. Sprint 12 does not implement the Sprint 13
Intent Router, autonomous planning or natural-language answer generation.

## Sprint 14 Watchlist and notification flow

`Snapshot/Activity/Trend/Potential commit → Celery Alert evaluation → deterministic AlertService →
PostgreSQL Alert Evidence → Daily/Weekly ReportService → REST/MCP read → Vue/PM Copilot`。
Watchlist 写入仅由明确 REST 操作进入 Service；MCP 与 PM Copilot 只有读取能力。
# Sprint 15 production boundary

公共读 API 与用户域分离。用户身份从 DRF Authentication 进入 Service Layer；Watchlist/Alert Receipt/Report 使用 PostgreSQL User FK，Copilot Session 使用 `owner_id + session_id` Redis namespace，MCP 调用通过 actor context 保持同一身份。反向代理是唯一公网入口，DB/Redis 仅内部网络可达。

Trend/Potential 持久化成功后额外写入幂等 Score History，再由 Alert Service 比较两个真实时间桶。该路径不改变评分算法，也不回填过去分数。

Copilot 成功轮次使用 `Runtime → CopilotHistoryService → PostgreSQL` 保存用户私有问答；Redis 仍只保存
有 TTL 的有界上下文。历史 REST API 不从 Redis 枚举数据，所有查询和删除均限定 authenticated owner。

## V1 Data Maturity activation

`Celery Beat → Redis global lock → DataMaturityService → capability UPSERT → first READY transition →
bounded scoring batches → existing Trend/Potential/Score History/Alert chain`。

ACTIVE Star增强模型存在时，日成熟度检查还会投递有界 ML 任务：只选择已经具备可靠 V2 Feature、
且当前 Model Version 尚无预测的 Repository。预测结果按模型版本冻结，重复调度由 Redis Lock、
数据库唯一约束和“已存在结果”过滤共同保持幂等。

Dashboard 同时保留 Category Distribution 与版本化 Category Trend 的响应契约，并由
`capability_status` 自动选择展示。详细门禁见 `DATA_MATURITY.md`。

## Repository 中文本地化

`Repository Detail API → content-hash cache lookup → immediate original-content fallback →
interactive queue → dedicated Celery localization worker → LLM Provider → versioned cache`。

公共详情请求不调用 LLM。缓存缺失时 API 返回 `localization_status=PENDING`、原始简介与 Topic，
并通过 Redis cache key 在10分钟窗口内幂等派发一次后台翻译。Vue 每3秒仅刷新 Detail，翻译完成后
自动替换为中文，最多检查20次；离开页面会清理 Timer。

生产 Celery 按职责拆分为单并发 Worker：`celery-worker` 消费 GitHub/Knowledge 后台任务，
`celery-scoring` 消费 `operations,scoring`，`celery-interactive` 只消费 `interactive`。
全部使用 prefetch multiplier=1，防止不同工作负载互相阻塞。Snapshot 与 Activity 成功后通过 Redis
短期派发键合并同仓库重复 Trend 请求；完整链路为
`Trend → Potential/Learning/Enterprise → Alert`，Alert 只在 Potential 完成后触发一次。全库 Alert
扫描改为每日兜底，Capability/Retention 进入 `operations`，不会再排在普通评分任务末尾。

模型训练固定路由到独立 `celery-ml` Worker，只消费 `ml`、concurrency=1、prefetch=1，生产限制
1 CPU。后台 Worker 不再消费 `ml`，避免训练阻塞采集和 interactive 任务。
