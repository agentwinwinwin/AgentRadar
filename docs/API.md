# API

Sprint 6 提供只读 Dashboard/Project/Potential API。所有数据来自 AgentRadar PostgreSQL；前端不直接访问
GitHub。API 保留 JSON `null` 表示数据不足，调用方不得将其转换为 `0`。

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health/` | Backend health |
| GET | `/api/v1/dashboard` | Dashboard 汇总、Top Trend、Breakout、Hype、Lifecycle 与 Category |
| GET | `/api/v1/projects` | Repository Discover、过滤、排序和分页 |
| GET | `/api/v1/projects/{id}` | Repository 当前详情、最新 Snapshot/Activity/Trend 摘要 |
| GET | `/api/v1/projects/{id}/metrics` | Snapshot、Activity、Release 和 Trend 图表序列 |
| GET | `/api/v1/projects/{id}/trend` | Sprint 4 Trend Engine 分数、完整度、版本和 Evidence |
| GET | `/api/v1/projects/{id}/potential` | Sprint 6 Potential、confidence、候选状态和 Evidence |
| GET | `/api/v1/projects/{id}/forecast` | Sprint 8 Forecast 状态；未就绪时回退 Potential |
| GET | `/api/v1/projects/{id}/learning` | Sprint 10 Learning Score、confidence 与 Evidence |
| GET | `/api/v1/projects/{id}/enterprise` | Sprint 10 Enterprise Score、建议、confidence 与 Evidence |
| POST | `/api/v1/copilot/chat` | Sprint 13 PM Copilot 自然语言分析与可追溯 Evidence |
| POST | `/api/v1/copilot/chat/stream` | PM Copilot SSE 流式状态、答案片段与最终 Evidence |
| GET | `/api/v1/copilot/history` | 分页读取当前用户未删除的历史会话 |
| GET/DELETE | `/api/v1/copilot/history/{id}` | 查看完整历史问答或删除当前用户会话 |
| GET | `/api/v1/projects/{id}/community` | 公开读取项目点赞数与最近三条评论摘要 |
| POST/DELETE | `/api/v1/projects/{id}/like` | 登录用户幂等点赞或取消点赞 |
| GET | `/api/v1/projects/{id}/comments` | 公开分页读取项目全部评论，每页20条 |
| POST | `/api/v1/projects/{id}/comments` | 登录用户发表评论（1～2000 字符） |

`GET /api/v1/projects/{id}` 的 `localization_status` 可为 `PENDING`、`TRANSLATED` 或 `FALLBACK`。
`PENDING` 时 `description_zh/topics_zh` 暂时承载 GitHub 原文，后台 Celery 完成翻译后相同 Endpoint
自动返回持久化中文缓存；该读请求不会同步等待 LLM。

项目详情返回规范化 `github_url=https://github.com/{owner}/{name}`，供前端跳转真实 GitHub
Repository。社区互动不修改 GitHub Star、Repository Pool、Trend、Potential 或 Forecast。
评论作为用户内容以纯文本展示，不解释或执行其中的 HTML/指令。所有用户评论均可在独立项目评论页
公开查看；创建评论仍必须登录。

项目详情同时返回 `description_zh`、`topics_zh` 与 `localization_status`。中文本地化以 GitHub
简介和 Topic 的 SHA-256 做 Change Detection；内容未变化时只读 PostgreSQL 缓存。原始英文数据
继续保留且不覆盖。Provider 不可用或响应无效时返回中文确定性兜底说明并标记 `FALLBACK`。

## PM Copilot

`POST /api/v1/copilot/chat` 接受 `message`（1～4000 字符）及可选 `session_id`，返回中文回答、
Intent/置信度、Skill/版本、状态、建议、警告、Evidence、trace ID 和 session ID。前端不接收 LLM Key，
也不直接请求 GitHub/MCP。LLM 未配置时返回 `LLM_NOT_CONFIGURED`，意图无法可靠识别时返回
`INTENT_UNRESOLVED`；这些状态不会退化为无 Evidence 的自由回答。
当前Intent覆盖普通项目发现、趋势/高潜排行、未来预测、学习/企业推荐、分析/比较、项目知识、
关注/提醒/报告和系统说明。排行 `limit` 支持1～20；Category为可选条件。项目知识查询词只传给
Knowledge Tool，不会作为未知字段传给 `search_projects`。
响应同时返回 `repository_links[]`（`repository_id` + `full_name`），该映射只来自已执行 Tool 结果，
用于前端将回答中完整项目名连接到站内详情页。历史旧回答在读取时仅对真实 Repository 表中存在的
`owner/repository` 名称补充映射，不将任意文本解释为 URL。

成功完成的每轮问答会按认证用户持久化到 Copilot History。列表只返回标题、消息数和时间；
详情返回该会话问答及已持久化 Evidence。查看和删除都使用 owner 查询级过滤，其他用户统一获得
404，避免泄漏资源是否存在。

流式端点使用认证 POST + `text/event-stream`，事件依次为 `status`、`delta`、`complete`；失败为
`error`。DeepSeek/OpenAI-compatible Provider 使用上游 SSE，正确忽略 keep-alive 并读取 usage。Tool 与
Evidence 先完整落定；开始生成后，Backend 仅解码 JSON 中的 `answer` 字段并将真实 Provider
delta 实时转发，不转发原始 JSON 或 reasoning。结束时 `complete` 仍携带经完整 Contract 校验的
Evidence、Trace、Session 和状态。Forecast 安全敏感回答在禁止概率校验前不实时外发。

## Project Discover

`GET /api/v1/projects` 支持：

- `q`、`category`、`language`、`license`
- `min_stars`、`max_stars`、`trend_min`、`potential_min`、`learning_min`、`enterprise_min`
- `lifecycle`
- `sort=trend|-trend|potential|-potential|learning|-learning|enterprise|-enterprise|stars|-stars|updated|-updated`
- `page`、`page_size`（最大 100）

返回 DRF 标准分页结构：`count`、`next`、`previous`、`results`。所有分数过滤范围为
0～100，Star 范围必须有效。Learning/Enterprise 正式排序与最低值过滤只纳入达到配置置信度门槛的行。

## Learning and Enterprise evidence

两个 API 只读取版本化持久化评分，不在请求期调用 GitHub 或 LLM。Evidence 的组件状态明确区分
`VALUE`、`MISSING` 与 `INSUFFICIENT_HISTORY`；Knowledge 状态明确区分 `NOT_INGESTED` 与
`DOCUMENT_NOT_FOUND`。低于排名置信度门槛时 `ranking_eligible=false`，但详情仍返回原始分数、
confidence 与依据。公式及语义见 `SCORES.md`。

## Project Metrics

`GET /api/v1/projects/{id}/metrics?range=7d|30d|90d`，默认 `30d`。返回：

- `snapshots`: Star、Fork、Subscriber、Open Issue 与 Snapshot 完整度时间序列
- `activity`: Commit、PR、Issue、Contributor、Release 活跃度时间序列
- `releases`: 选定时间范围内的 Release
- `trend_history`: 已持久化的 Trend 计算结果
- `potential_history`: 已持久化的 Potential 计算结果

## Trend and evidence

Trend API 只读取 Sprint 4 已持久化结果，不在请求中重新计算，也不调用 LLM。结果包含各组件分数、
`trend_score`、`hype_risk`、`hype_risk_status`、`lifecycle_stage`、
`data_completeness`、`algorithm_version`、`calculated_at` 和结构化 `evidence`。

Top Trend 正式排行榜只纳入 `data_completeness >= 0.50` 且 Trend Score 非 NULL 的项目；
所有分数降序查询显式使用 NULLS LAST。数据积累中的项目仍保留在 Discover 结果中，但不参与
正式 Top Trend 排名。
无评分时返回 `status=NOT_AVAILABLE`；Hype 数据不足时为
`hype_risk=null`、`hype_risk_status=INSUFFICIENT_HISTORY`。

## Potential and evidence

Potential API 只读取 `potential-v1.0.0` 持久化结果，返回 `potential_score`、`confidence`、
`algorithm_version`、候选标记与 Evidence。Evidence 包含 Sprint 4 来源版本、各输入、权重、
完整度、Hype penalty、缺失输入和候选阈值。无结果时 `potential_score=null` 且
`status=NOT_AVAILABLE`。

Dashboard 增加 `high_potential_projects` 与 `breakout_candidates`；项目摘要增加 Potential、
confidence 和候选状态。High Potential Ranking 按 Potential、confidence、Trend 降序，排名依据
可通过项目 Potential API 解释。

Potential Score 不是 Forecast Probability。Sprint 6 不返回预测概率、未来上涨概率或模型输出。

Post-V1 展示兼容：项目摘要新增 `potential_score_source`、`deterministic_potential_score`、
`forecast_percentile` 与 `forecast_sample_at`。仅当 ACTIVE `feature-v2.0.0` 模型存在48小时内的有效
预测百分位时，摘要中的 `potential_score` 和高潜榜排序切换为该百分位；否则逐项目回退确定性
Potential。Dashboard 的 `high_potential_ranking` 明确返回当前来源、回退来源和算法版本。
`/projects/{id}/potential` 仍返回确定性 Potential 及其 Evidence，不覆盖历史审计结果。

Sprint 7 不新增面向前端的 Dataset 或 Forecast API。Dataset 通过受控管理命令与 Celery
`github_backfill` 队列构建；Forecast 状态保持 `NOT_READY`。
## Forecast

`GET /api/v1/projects/{id}/forecast`

Forecast V1 端点只选择 `model_name=activity-growth-30d`、`feature_version=feature-v1.0.0` 的
ACTIVE 二分类模型，不会误选 Star 增强模型。READY 结果额外返回
`forecast_type=ACTIVITY_FORECAST_V1` 和经过白名单过滤的 `input_features`，供详情页解释本次预测；
Repository ID、内部 provenance 及未授权字段不会返回。

没有 ACTIVE 模型或没有合格预测时返回：

```json
{
  "status": "NOT_READY",
  "forecast": null,
  "fallback": "POTENTIAL_SCORE",
  "definition": "未来30天进入同 Category 高开发活跃增长组的概率"
}
```

只有显式激活且通过全部门禁的模型才允许返回 `READY` 和概率。

## MCP interface

Sprint 11 does not add a public HTTP endpoint. MCP uses JSON-RPC over stdio and proxies the Internal
Tool Registry. Tool schemas, catalog, errors, limits and Forecast `NOT_READY` behavior are in
`MCP.md`. Browser clients continue to use DRF; MCP is for future trusted AgentRadar clients.

## Sprint 14 Watchlist / Alert / Report

- `GET|POST /api/v1/watchlist`：查看或明确添加关注。
- `DELETE /api/v1/watchlist/{repository_id}`：明确取消关注，重复取消安全。
- `GET /api/v1/alerts`：按 Repository、状态、类型读取确定性 Alert。
- `GET|PATCH /api/v1/alerts/{id}`：读取 Evidence 或更新 `UNREAD/READ/DISMISSED`。
- `GET|POST /api/v1/reports`：读取或明确生成 `DAILY/WEEKLY` 报告。
- `GET /api/v1/reports/{id}`：读取结构化报告详情。

Repository Detail 增加 `is_watchlisted`。Secret 不进入响应或前端。

## Sprint 15 Authentication and operations

- `POST /api/v1/auth/login`：用户名/密码换取 DRF Token；认证端点独立限流。响应包含 `expires_at` 与 `expires_in`，默认有效期为固定 3 小时；再次登录会签发新 Token 并重新计时。
- `GET /api/v1/auth/me`：读取当前身份。
- `POST /api/v1/auth/logout`：撤销当前用户 Token。
- Watchlist、Alert、Report、Copilot 均要求认证，并按 User 做服务层和查询层隔离。
- `GET /api/v1/health/live`：匿名 liveness。
- `GET /api/v1/health/ready`：匿名 readiness，不返回 Secret。
- `GET /api/v1/operations/status`：仅 staff 可访问。
- `GET /api/v1/operations/control-center`：仅 staff 可访问，返回依赖状态、Capability 成熟度、
  Forecast 产品状态、Model Registry 的 Validation/Test、Dataset Gate、Feature Importance、Artifact
  Hash 和激活阻塞原因；不返回 Artifact 路径或 Secret。
- `POST /api/v1/operations/models/{model_version}/activate`：仅 staff 可访问。请求体必须包含与 URL
  完全一致的 `confirmation=model_version`；后端仍会重新执行 Dataset、VALIDATED 状态和全部指标
  门禁。普通用户即使手工构造请求也返回403。

Dashboard 的 `category_trend` 返回 `status`、`fallback`、`data_as_of`、`data_coverage`、
`algorithm_version`、`reason` 和 `results`。ACCUMULATING/DEGRADED 时 fallback 为
`CATEGORY_DISTRIBUTION`；READY 时 results 为 `category-trend-v1.0.0` 分类趋势。

`GET /api/v1/operations/status` 的 `capabilities` 列表额外返回每项能力的 status、coverage、
first_ready_at、last_evaluated_at、reason、algorithm_version 与 metrics。

通用匿名/认证限流分别由 `API_ANON_RATE`、`API_USER_RATE` 配置，Agent 与认证端点使用独立 scope。所有响应带 `X-Request-ID`。请求体默认上限1 MiB。

管理员模型训练 API：`POST /operations/training/check` 重新检查真实门禁；
`POST /operations/training/start` 精确确认后返回 202；`GET /operations/training/runs/{id}` 查询状态。
均仅限 staff，不自动激活、不返回 Artifact 路径或 Secret，重复启动返回409。
