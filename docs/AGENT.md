# PM Copilot Agent V1

Sprint 13 只提供一个 PM Copilot Agent。执行链路固定为：

`用户问题 → LLM Intent Router → Skill Registry → 版本化 Skill → MCP Client → MCP Server → 只读 Tool → Service/PostgreSQL/pgvector → Evidence → LLM 中文回答`。

Agent 禁止直接访问 ORM、GitHub、评分算法、模型 Artifact 或 Tool Registry。Repository 名称通过
所选 Skill 白名单内的 `search_projects` MCP Tool 解析，LLM 不生成或记忆数据库 ID。

## LLM Provider

Provider 由后端环境配置。`openai` 使用 Responses API；`deepseek` 和
`openai_compatible` 使用兼容 Chat Completions。推荐 DeepSeek 配置为：

```text
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-pro
DEEPSEEK_API_KEY=<server-only secret>
```

Key 只从进程环境读取。Intent 输出必须满足严格 JSON Contract；首次输出无效时仅允许一次修复，
再次无效返回 `INTENT_UNRESOLVED`。最终回答也必须满足 JSON Contract。

## Intent 与 Skill

| Intent | Skill |
| --- | --- |
| `PROJECT_DISCOVERY` | `project-discovery` |
| `TREND_DISCOVERY` | `trend-research` |
| `POTENTIAL_DISCOVERY` | `potential-research` |
| `FUTURE_PREDICTION` | `future-prediction` |
| `LEARNING_RECOMMENDATION` | `learning-recommendation` |
| `ENTERPRISE_SELECTION` | `enterprise-selection` |
| `PROJECT_ANALYSIS` | `project-analysis` |
| `PROJECT_COMPARISON` | `project-comparison` |
| `WATCHLIST_QUERY` | `watchlist-query` |
| `ALERT_QUERY` | `alert-query` |
| `REPORT_QUERY` | `report-query` |
| `PROJECT_KNOWLEDGE` | `project-knowledge` |
| `SYSTEM_HELP` | `system-help` |

每个 Skill 的 allowed tools、预算、Evidence、Fallback 和 Stop Condition 仍由不可变版本的
`skills/*/SKILL.md` 定义。为支持 Repository 名称解析，Future/Analysis/Comparison 升级到 v1.1.0；
原有算法与 Tool 行为未改变。

## Session 与安全

Redis 只保存短期最近轮次、已解析实体、用户约束与最后 Intent，并设置 TTL；不保存完整 Tool Evidence。
GitHub/RAG 内容始终标记为不可信外部内容，注入式指令在上下文构建时移除。最终回答只允许引用 Tool
Evidence；NULL 不得解释为 0，`NOT_INGESTED` 不得解释为文档不存在，Forecast NOT_READY 时禁止概率。

Sprint 14 仅增加三个只读查询 Intent。PM Copilot 可以读取关注列表、项目 Alert 与日报/周报；不能自主
添加或取消关注，也不能让 LLM 决定 Alert 是否触发或重算报告事实。

Trace 记录 trace/session、Intent/Skill、Tool 名称与数量、耗时、Evidence 数、warning、停止原因、
Provider/Model 和 token usage，不记录 Secret 或完整不可信正文。

Agent Router 可产生 `user_goal`、`risk_preference` 等工作流上下文，但 Skill Executor 只允许将目标
Tool `inputSchema.properties` 明确声明的字段传入 MCP。上下文字段不得透传为 Tool 参数；Skill 内固定
arguments 在过滤后合并，并继续由 Tool Schema 做最终严格校验。

## V1 意图覆盖增强

Router 当前将常见业务问题拆成13条明确路径：普通项目发现、趋势排行、高潜排行、未来活跃预测、
学习推荐、企业选型、单项目综合分析、项目比较、项目知识问答、关注查询、提醒查询、报告查询和
系统说明。排行问题支持1～20条，Category均为可选条件；“趋势前十”不再被强制要求Category，
“高潜前十”不会误走Forecast。项目用途、安装、架构、能力、版本和安全问题只通过Knowledge Skill
检索已入库证据；指标含义、采集、训练和产品使用问题只读取版本化可信系统说明。

同一Intent的连续追问可继承用户约束；切换Intent时不继承旧Category等筛选条件，防止上一轮问题
污染下一轮。Learning/Enterprise候选搜索默认返回10项供回答展示，但昂贵的深入评分和Knowledge
取证仍限制在前三项，控制Tool预算与响应时间。

## Sprint 15 runtime limits

Copilot API 要求认证并使用独立 Agent throttle；Session key 包含 owner ID，TTL、turn/context/evidence
上限继续生效，新增总 Token 预算。用户之间不能读取或续接彼此 session。LLM 失败不得影响确定性评分、
Alert 或结构化报告，日志不得记录 Prompt、Authorization 或模型密钥。

## Validated streaming response

DeepSeek/OpenAI-compatible 最终答案调用支持上游 `stream=true`。Tool/Skill/Evidence 先完整执行并
构建受信上下文，然后 Backend 从 Provider JSON stream 中只提取已解码的 `answer` 字符串增量，
通过 SSE 实时发往 Browser。原始 JSON、recommendations/warnings token 与 thinking/reasoning 不暴露；
Provider 结束后仍必须通过完整 Schema 验证，`complete` 才是权威结果。Forecast 安全敏感场景保持缓冲，
通过概率文案检查后才返回，避免未激活 Forecast 的禁止性概率文案暂时泄漏。

SSE Runtime 在专用工作线程执行。Tool timeout guard 在主线程使用 `SIGALRM` 预占超时，在 SSE
工作线程使用同步耗时门禁；不得在非主线程调用 Python signal API。
