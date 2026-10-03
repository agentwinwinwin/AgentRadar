# Database

Sprint 0 uses PostgreSQL 16 with the pgvector image in Docker Compose. Django tests default to SQLite so foundation tests do not require external services.

## Sprint 1 tables

- `repositories`: verified current Repository fields from the master specification and Sprint -1
  dictionary. Unique `github_id` is the stable sync identity; `full_name` is also unique.
- `topics`: unique displayed and normalized topic names.
- `repository_topics`: many-to-many join with database constraint
  `UNIQUE(repository_id, topic_id)`.
- `github_discovery_queries`: editable, uniquely named Discovery Query Pool with active flag.

Indexes cover category, stars, GitHub pushed time, last sync time and archived state as required.
Nullable GitHub strings and timestamps remain NULL when GitHub returns null. `open_issues` preserves
GitHub's verified `open_issues_count` semantics, which includes open pull requests.

Migrations:

- `repositories.0001_initial`: creates the Sprint 1 domain tables and relationship constraint.
- `repositories.0002_alter_repository_stars`: adds the required stars index.
- `repositories.0003_seed_discovery_queries`: seeds the V1 query pool with a reversible data
  migration.

No Snapshot, Activity, Contributor, Release, score, RAG or forecast table is created in Sprint 1.

## Sprint 2 tables

`repository_snapshots` stores:

- repository foreign key
- `snapshot_at`, UTC `snapshot_date`, six-hour `snapshot_bucket`
- nullable stars, forks, subscribers, open issues and GitHub pushed time
- `data_completeness` in `[0, 1]`
- creation timestamp

Database protection:

- `UNIQUE(repository_id, snapshot_bucket)` prevents concurrent duplicate buckets.
- `snapshot_completeness_between_zero_and_one` rejects invalid completeness.
- Positive integer fields retain database non-negative checks while allowing NULL.

Sprint 2 migrations:

- `repositories.0004_*`: makes current Repository counters nullable so missing GitHub data is not
  silently converted to zero.
- `snapshots.0001_initial`: creates `repository_snapshots` and its constraints.

## Sprint 3 tables

`repository_activity_metrics` 按 UTC 日期保存 7/30/90 天 Commit、PR、Issue、Contributor、
Release 与活跃间隔指标。所有外部统计字段允许 NULL；GitHub Search 返回
`incomplete_results=true` 时对应字段写 NULL，不能与真实的 0 混淆。

数据库保护：

- `UNIQUE(repository_id, metric_date)` 保证每日 Activity Task 幂等。
- `contributors.github_user_id` 唯一，保存 GitHub 用户当前身份信息。
- `UNIQUE(repository_id, contributor_id)` 保证 Repository Contributor 关系幂等。
- `repository_releases.github_release_id` 唯一，Release 内容以 SHA-256 标识当前版本。

Sprint 3 Migration：

- `activities.0001_initial`：创建 Activity Metric、Contributor、Repository Contributor、
  Repository Release 四张表及其唯一约束。

## Sprint 4 tables

`repository_trend_scores` 保存 Trend 及其七个组件、Hype Risk、Lifecycle、完整度、算法版本、
计算时间和可解释 evidence。所有可能因源数据不足而缺失的 Score 字段允许 NULL。

数据库保护：

- `UNIQUE(repository_id, algorithm_version)` 保证同一算法版本重复评分为 UPSERT，同时保留
  未来新算法版本的独立记录。
- `trend_completeness_between_zero_and_one` 保证完整度处于 `[0,1]`。

Sprint 4 Migration：

- `trends.0001_initial`：创建 `repository_trend_scores` 和上述约束。

## Sprint 6 tables

`repository_potential_scores` 保存确定性 Potential Score、confidence、算法版本、结构化
evidence 与计算时间。Potential 可以因 Trend 不可用而保持 NULL，不能转换为 0。

数据库保护：

- `UNIQUE(repository_id, algorithm_version)` 保证同一 Potential 算法版本重复计算为 UPSERT。
- `potential_confidence_between_zero_and_one` 保证 confidence 位于 `[0,1]`。

Sprint 6 Migration：

- `potentials.0001_initial`：创建 `repository_potential_scores` 和上述约束。

Sprint 6 未创建 Category Snapshot、Historical Dataset、Training Sample、Model Registry 或
Forecast 表。

## Sprint 7 tables

`historical_activity_windows` 保存任意闭区间的 Commit、PR、Issue、Contributor、Release
历史活动统计、完整度、来源元数据及明确的 `data_origin`。Sprint 7 写入
`BACKFILLED`，不会写入或伪造 Repository Snapshot。

`training_samples` 保存 Repository、`sample_at`、Feature/Label 窗口、Category、Age Cohort、
features JSON、二元 label、label score、`feature_version`、`label_version`、来源和 Label
Evidence。同一 Repository 可有多个 sample_at。

数据库保护：

- Historical Window：repository + start + end + origin 唯一；start <= end；完整度 `[0,1]`。
- Training Sample：repository + sample_at + feature_version + label_version 唯一；label 仅
  0/1；label score `[0,100]`。

Sprint 7 Migration：

- `datasets.0001_initial`：创建上述两张表及约束。
- `datasets.0002_historicalbackfillbatch_and_items`：创建大规模历史回填批次和逐仓库/时间点
  检查点表。Item 使用 `(batch, repository, sample_date)` 唯一约束，保存状态、尝试次数、
  窗口写入数、脱敏错误摘要和各 Endpoint 请求量，支持幂等断点续跑。
- `datasets.0003_acquisitionqueryshard_repositorypool_and_more`：创建 Repository Pool、Membership
  和 Acquisition Query Shard。Pool 支持 CANDIDATE/TRACKED/TRAINING 与 DRAFT/CONFIRMED；
  Membership 保存选择时的 Category、Star Bucket、Age Cohort、Activity Level、原因和分层排名，
  并以 `(pool, repository)` 唯一约束保证幂等。
- `datasets.0004_historicalbackfillbatch_rate_limit_state`：保存批次各 GitHub 资源池的
  remaining/reset 状态。
- `datasets.0005_historicalsourcecache_historicalactivitybucket_and_more`：创建版本化 Historical
  Activity Bucket、Contributor Week 和 Repository Source Cache。Bucket 使用
  `(repository, start, end, kind)` 唯一约束；Contributor Week 使用
  `(repository, contributor_key, week_start)` 唯一约束。
- `datasets.0006_historicalactivitybucket_historical_bucket_completeness_between_zero_and_one`：
  在数据库层保证 Bucket completeness 位于 `[0,1]`。

没有创建 Model Registry 或 Forecast 表。

## Sprint 8 tables

### `ml_models`

保存 model/feature/label version、算法、训练时间范围、Dataset Gate 快照、Validation/Test 完整指标、
Feature Importance、artifact 路径与 SHA-256、状态。`model_version` 唯一；训练默认仅到
`VALIDATED`，不能自动 ACTIVE。

### `repository_forecasts`

保存 Repository、Model、sample_at、30 天 horizon、高增长概率、二元预测、confidence 与完整 Feature
Snapshot。唯一约束为 `(repository, model_version, sample_at)`，prediction 仅允许 0/1。

Migration：`forecasts/0001_initial.py`。

Post-V1 Migration `forecasts.0003_repositoryforecast_predicted_percentile` 为 Forecast 增加可空
`predicted_activity_percentile`（数据库约束0～100）与 `percentile_model_version`。字段只承载回归/
排序模型直接产生的百分位；高增长分类概率继续保存在原字段，二者禁止互相替代。

Post-V1 管理员训练流程使用 `model_training_runs` 持久化训练请求、门禁/切分快照、Task ID、请求人、
时间、脱敏失败原因及候选模型结果。部分唯一约束保证最多一个 `QUEUED/RUNNING` 训练；Migration 为
`forecasts.0002_modeltrainingrun`。
Migration `datasets.0008` 新增可空的 `future_activity_percentile`、`binary_top20_label` 和
`label_cohort_size`，用于 `label-v1.2.0` 的显式双 Target。数据库约束保证 Percentile 位于
0～100、binary 只能为 0/1；旧 Label 版本行保持 NULL，未回填或覆盖。

分类与回归 artifact 保存于 Compose `ml_artifacts` 命名卷的 `/ml/artifacts`，Backend 与
Celery Worker 共享。Registry 保存路径和 SHA-256；真实训练后逐文件校验存在且摘要一致。

## Sprint 8.5 monitoring fields

Migration `repositories.0005` adds `monitoring_tier`, `monitoring_enabled`, `last_snapshot_at` and
indexed `next_snapshot_at`. Migration `snapshots.0002` adds GitHub updated time, archive state,
watcher alias and explicit `data_origin=OBSERVED`. The existing
`UNIQUE(repository_id, snapshot_bucket)` is unchanged.

## Sprint 9 Knowledge tables

- `knowledge_documents`: versioned source identity/content/hash/URL/timestamps/metadata/active flag;
  unique `(repository, source_type, external_id)`.
- `knowledge_chunks`: heading-aware content, token/hash/metadata and pgvector `vector(384)` with
  embedding model/version; unique `(document, chunk_index, embedding_version)`.
- `knowledge_sync_states`: per-repository last/next sync, status and cost statistics.

Migration `knowledge.0001` ensures the PostgreSQL `vector` Extension and creates these tables.

## Sprint 10 score tables

- `repository_learning_scores`: nullable score、confidence、algorithm version、Evidence 与计算时间。
- `repository_enterprise_scores`: 同上，并保存 `ADOPT/POC/WATCH/AVOID` recommendation。

两表均以 `(repository, algorithm_version)` 唯一约束保证版本化 UPSERT，并以数据库 Check
Constraint 保证 confidence 位于 `[0,1]`。Migration 分别为 `learning.0001_initial` 与
`enterprise.0001_initial`；NULL 输入不会被数据库默认值转换为零。

V1 全量评分扩展 Migration `learning.0002_repositoryassessmentevidence` 新增
`repository_assessment_evidence`。每个 Repository 最多一条轻量文件 Metadata 证据，记录检查状态、
各白名单能力的 nullable boolean、命中路径、请求数、时间与脱敏错误。未检查为 NULL，不会写成 false；
该表不存文件正文或 Embedding，也不修改已有 Score、Snapshot、Dataset 或 Model Registry。

## Sprint 14 tables

Migration `watchlists.0001_initial` 新增 `watchlists`、`watchlist_items`、`watchlist_events`、
`alerts` 和 `scheduled_reports`。Watchlist item 唯一于列表与 Repository；Alert 唯一于
Repository、类型、规则版本和事件桶；Report 唯一于 owner、类型、周期和规则版本。

Sprint 15 Migration `watchlists.0002_user_isolation` 将 Watchlist、Event、Report 绑定 Django User，Alert 的用户态拆为 `alert_receipts(owner, alert, status)`，同一 Alert 在用户之间互不影响。数据迁移只把旧本地数据绑定到不可登录的 `legacy-local` 用户，不删除旧记录。

`operations.0001_initial` 新增 `repository_score_history`。唯一键为 Repository、Score Type、Algorithm Version、6小时 History Bucket，并为 Repository/Type/Time 和 Type/Time 建索引。该表只记录上线后的真实 Trend/Potential 计算，不执行历史补写。

## Post-Sprint 15 repository community tables

Migration `interactions.0001_initial` 新增 `repository_likes` 与 `repository_comments`：

- Like 以 `(repository, user)` 数据库唯一约束保证重复点赞幂等。
- Comment 绑定 Repository 与 Django User，正文上限 2000 字符，按创建时间倒序读取。
- Repository 删除时关联互动按外键级联；用户删除时其互动同步删除。
- 两表均建立 Repository + 创建时间索引，不修改任何 Snapshot、评分或训练数据。

Migration `repositories.0008_repositorylocalization` 新增一对一 `repository_localizations`，保存
中文简介、中文 Topic、源内容 SHA-256、Provider/Model、状态与翻译时间。源内容不变时复用缓存，
GitHub 原始字段保持不变。

## V1 Data Maturity tables

Migration `capabilities.0001_initial` 新增：

- `data_capabilities`：每种能力一行，保存状态、覆盖率、数据时间、首次 READY 时间、评估时间、原因、
  算法版本和审计 metrics；状态与覆盖率均有数据库约束。
- `category_trend_metrics`：保存 `category-trend-v1.0.0` 的分类聚合结果；
  `(category, algorithm_version)` 唯一，覆盖率有数据库约束。

两表均为可重建派生状态，不修改 Repository Snapshot、评分、Dataset 或 Model Registry。

## Post-Sprint 15 Copilot history tables

Migration `agent.0001_initial` 新增 `copilot_conversations` 与 `copilot_messages`：

- Conversation 以 `(owner, session_id)` 数据库唯一约束保证用户私有会话边界。
- Message 保存 USER/ASSISTANT 正文；Assistant response 仅保存前端恢复展示必要的结果、Evidence、
  Intent 和版本元数据，不保存 Prompt、Key、Provider 原始 JSON 或内部 Trace 详情。
- Conversation 删除使用外键级联删除 Message，并同步删除对应 Redis 短期上下文，防止被删会话继续。
