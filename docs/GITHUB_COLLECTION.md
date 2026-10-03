# GitHub Collection

## Sprint 1 access boundary

All GitHub access enters through `GitHubClientProtocol`. Production commands use
`RealGitHubClient`; tests use `FakeGitHubClient`. Views, services and management commands must not
make direct HTTP requests to GitHub.

Sprint 1 uses only capabilities verified in Sprint -1:

- `GET /repos/{owner}/{repo}` for current Repository metadata.
- `GET /search/repositories` for discovery.

The REST API version is fixed to `2022-11-28`. Authentication is optional for public repositories
and loaded from `GITHUB_TOKEN`. The token is never exposed to the frontend.

## Discovery Query Pool

The data migration seeds the documented V1 queries into `github_discovery_queries`. Administrators
may enable, disable or add query partitions without modifying task or service code. Every search is
combined with:

```text
archived:false fork:false stars:>10
```

The service fetches at most ten pages of 100 results per query because GitHub Search exposes only
the first 1,000 matches. `incomplete_queries` and `truncated_queries` are returned explicitly. Large
queries require narrower administrator-defined partitions; the service never claims exhaustive
coverage beyond GitHub's verified boundary.

Discovery defensively skips fork and archived results even though qualifiers are present, because
the search index can lag current repository state.

## Commands

```bash
python manage.py discover_repositories --per-query 100 --pages-per-query 10
python manage.py sync_repository owner/repository
```

Both commands use `RealGitHubClient`. Unit and integration tests use `FakeGitHubClient` and do not
consume GitHub rate limits.

## Error behavior

- Invalid repository names and request parameters fail before the HTTP request.
- 404 becomes `GitHubNotFoundError`.
- Exhausted primary rate limits and HTTP 429 become `GitHubRateLimitError`, preserving reset time.
- Network failures, malformed JSON and other HTTP failures become `GitHubClientError`.
- Search page 11+ is rejected because it cannot be accessed reliably under the 1,000-result cap.

## Sprint 2 Snapshot collection

Snapshot tasks call `GitHubClientProtocol.get_repository`; Celery code contains no direct GitHub
HTTP. The verified current fields `stargazers_count`, `forks_count`, `subscribers_count`,
`open_issues_count` and `pushed_at` are observed. Missing values remain NULL.

Repository fetch occurs before the database transaction. Repository current-state update and
Snapshot UPSERT occur in one transaction, and downstream notification is registered only with
`transaction.on_commit`.

## Sprint 3 Activity collection

所有请求继续由 `GitHubClientProtocol` / `RealGitHubClient` 发起：

- Commit：`GET /search/commits`，使用 `committer-date` 窄时间窗口与 `total_count`。
- PR / Issue：`GET /search/issues`，使用 `type`、created/merged/closed 日期限定与
  `total_count`。
- Contributor：分页读取 `GET /repos/{owner}/{repo}/contributors`。
- Contributor Statistics：读取 `/stats/contributors`；HTTP 202 返回 pending 状态，Celery
  使用 `Retry-After`（缺失时 60 秒）有限重试，pending 时不写部分 Activity 数据。
- Release：分页读取 `/releases`，以 release id UPSERT；draft 不计入活跃统计。
- Community：读取 `/community/profile`，同步当前 `health_percentage`。

Search `incomplete_results=true` 时保留 GitHub 报告的 total 供诊断，但业务 count 返回
NULL，Activity Metric 对应字段写 NULL。任务复用 repository Redis Lock，并由
`UNIQUE(repository_id, metric_date)` 提供第二层幂等保护。

生产调度采用到期分层而非每日全量扫描：HOT/NEW/RISING 每日、NORMAL 每3日、STABLE 每7日、
DORMANT 每30日。Beat 每小时最多派发50个到期 Repository，单 Worker 的 Activity Task 限速为
每分钟1个（约11次 Search/分钟），并在 Search remaining 不高于安全保留值时暂停。GitHub 返回
限流时按 `X-RateLimit-Reset` 等待，不再固定10秒重试。该限速基于
当前单 Worker 部署；扩展 Worker 数量前必须引入全局 Search Token Bucket 或相应下调每 Worker
限速。

未配置 Token 时 Search 限额仅适合 smoke；生产 Activity 采集必须配置 GitHub Token 并按
Search rate limit 调度。Contributor Statistics 仍受 GitHub 最近 10,000 个默认分支 commits
统计边界限制。

## Sprint 7 Historical Backfill

历史回填继续只通过 `GitHubClientProtocol`。每个 sample date 获取 Feature 7/30 日窗口及未来
Label 30 日窗口的 Commit、PR、Issue Search count，并用 Contributor Statistics 周数据和
Release published time 补充 Contributor/Release 活动。

- Search incomplete 对应字段写 NULL，不当 0。
- Contributor Statistics 202 不写部分窗口，由 `github_backfill` Celery task 有限重试。
- HTTP `IncompleteRead` 等传输中断统一转换为 `GitHubClientError`，进入同一重试边界。
- 所有历史窗口标记 `BACKFILLED` 并保存 API 范围限制；不创建历史 Star Snapshot。
- 回填任务不进入 Beat，必须由管理员明确选择 Repository 与已结束的 sample date。

真实 smoke 对 `octocat/Hello-World` 的 202 缓存状态处理后成功写入三个完整窗口；重复 Dataset
Builder 只更新同一版本样本。

Sprint 8 大规模回填按持久化 Batch 分批选取真实 Discovery Repository，默认以 14 天间隔创建
多个 sample_at。批处理对 Contributor Statistics 202 遵循 `Retry-After` 并有限重试，按仓库复用
Contributor Statistics/Release 响应；Search、Contributor Statistics、Release 请求量以及等待/重试
次数逐 Item 记录。成功 Item 重跑时跳过，失败 Item 可在最大尝试次数内续跑。

Contributor Statistics 周数据必须完整覆盖目标窗口才计算活跃贡献者；没有覆盖时保存 NULL，禁止
以 0 冒充“无活跃贡献者”。

Sprint 8 的 `activity-bucket-v1.0.0` 将相邻 sample 的精确 30 日 Activity Search 结果物化为
不可重复的基础桶，并在 PostgreSQL 本地复用为 Feature/Label Window。Contributor Statistics
按周持久化、Release 日期缓存，每仓库只请求一次；7 日 Feature 只补 Commit/PR 两个尾桶请求。

## Sprint 8.5 Continuous Discovery and Snapshot

- 新项目每6小时按 `created` 窗口发现；近期活跃项目每日按 `pushed` 窗口刷新。
- 两者复用完整语义 Query Pool，Search 按 `github_id` 去重；新结果再取 Metadata、确定性分类、
  加入 Candidate 并创建首条 OBSERVED Snapshot，不自动加入 Training。
- Snapshot 改为每小时统一查询 `next_snapshot_at` 的 dispatcher，单批有上限，不为每个仓库创建
  Beat 项。
- Snapshot频率按训练与产品的实际时间粒度配置：HOT每6小时、RISING每12小时、新建前7天每12小时、
  NORMAL及CONFIRMED Training Pool每日、STABLE每3天、DORMANT每7天；训练数据仍按每日桶取值。
- 当前动态分层使用 `monitoring-priority-v1.1.0`：用户Watchlist、真实Star/Fork增长、近期开发活动、
  Release、Trend/Potential高置信信号和ACTIVE模型输出可升频；长期无推送项目降为STABLE/DORMANT；
  CONFIRMED Training Pool保留NORMAL最低覆盖，归档/禁用项目停止。NULL不按0解释，模型不是唯一门禁。
- 每日通过 `operations` 队列重评全部非Fork项目；Snapshot落库及Watchlist增删也即时重评。同层重复
  执行不滑动`next_snapshot_at`，避免项目永远不到期。生产3,228个项目只读模拟为HOT 172、NEW 208、
  RISING 55、NORMAL 2,109、STABLE 202、DORMANT 481、ARCHIVED 1，约195次Snapshot/小时。
- 生产单批上限调整为225，为当前稳态和小幅增长保留余量；Dispatcher 仍按
  `core.remaining - safety_floor` 截断实际派发量，
  不消耗保留额度。
- 降频保护期为60天真实Snapshot跨度：只有`data_origin=OBSERVED`的首尾快照达到60天后，项目才允许
  降到STABLE或DORMANT；不足60天最低保持NORMAL，BACKFILLED数据不得用于满足该门禁。
- 降频采用全条件门禁而非单项低分：30天Star增长≤10、Fork增长≤2、Commit≤10、PR≤5、
  活跃贡献者≤2，且无新Release、无Watchlist、非CONFIRMED Training覆盖、无高Trend/Potential/
  ACTIVE模型信号时才允许降频。任一核心30天指标为NULL均不得降频。
- Discovery 检查 Search/Core，Snapshot dispatcher 检查 Core；安全阈值以下暂停并有限重试。
- Star/Fork 历史只来自真实 OBSERVED Snapshot，覆盖不足时增长/速度/加速度保持 NULL。

## Sprint 9 Knowledge collection

README、Contents、Release及PR/Issue Search统一通过GitHubClient。只读取允许的Markdown与重要
根文档，Release最多5个，PR/Issue使用确定性高价值规则且各最多5个。文件先做类型和500KB大小
限制，再作为不可信文本解码。`content_hash`未变化时跳过Chunk与Embedding；不扫描源码树。
