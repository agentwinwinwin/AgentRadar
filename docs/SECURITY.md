# Security Baseline

- Secrets are loaded only from environment variables; `.env` is ignored.
- `.env.example` contains placeholders only.
- The frontend must never receive GitHub, LLM, embedding, database, or Redis credentials.
- `DJANGO_SECRET_KEY` must be replaced outside local development.
- GitHub and repository text is untrusted data and never becomes an instruction source.
- Production must disable Django debug mode and set explicit allowed hosts.
- Dependencies and containers must be updated through reviewed changes.
- `RealGitHubClient` reads `GITHUB_TOKEN` only from backend settings and sends it only to the
  configured GitHub API origin.
- The previously exposed GitHub token is treated as revoked. Replacement credentials are accepted
  only through `GITHUB_TOKEN` in the process environment and are never copied into tests or docs.
- Compose validation uses `docker compose config --quiet`; do not print resolved Compose
  configuration because it may contain interpolated credentials.
- Sprint 5 Vue code communicates only with `/api/v1`; GitHub credentials and GitHub transport remain
  backend-only.
- Repository descriptions and GitHub metadata remain untrusted data; Sprint 1 does not execute or
  render them as instructions.
- Sprint 9 treats README/Docs/Release/PR/Issue as `UNTRUSTED_EXTERNAL_CONTENT`; content is never
  interpolated into system/developer/tool instructions and is not executed.
- Knowledge files are Markdown-only, size bounded and base64/UTF-8 validated. Source URLs are
  evidence metadata, not trusted download or command targets.
- The local V1 embedding provider keeps repository text inside Backend infrastructure. Future
  external providers require explicit configuration, secret isolation and data-handling review.
- Sprint 11 MCP exposes only a fixed read-only business Tool whitelist over stdio. There is no
  arbitrary SQL, filesystem, shell, Python, GitHub collection, mutation, training or activation Tool.
- Tool schemas reject unknown fields and bound result sizes; calls enforce timeouts. Errors suppress
  stack traces and internal messages. Output never includes `.env`, credentials or process environment.
- Sprint 12 Skills may reference only Registry Tools marked `read_only=true`; startup validation
  rejects unknown, non-whitelisted or write Tools. Skill policies cannot run SQL, shell, Python,
  filesystem access, GitHub ingestion, model activation, Backfill or score writes.
- Skill Execution Trace contains only policy/version, Tool names, durations, statuses and Evidence
  counts. It never records credentials, environment values or complete untrusted document content.
- Sprint 13 LLM credentials are backend environment variables only (`OPENAI_API_KEY` or
  `DEEPSEEK_API_KEY`). Copilot API、Vue、session、Evidence 与 trace 均不得返回这些值。
- PM Copilot 使用严格 Intent JSON、单次有限修复、Skill Tool 白名单和预算。RAG/GitHub 文本只作为
  `UNTRUSTED_EXTERNAL_CONTENT`，注入式指令不会成为 system、developer 或 Tool 指令。
- Copilot SSE 只在 Tool/Skill/Evidence 上下文建立后开始，且只从 Provider JSON stream 提取解码后的
  `answer` 增量；原始 JSON、reasoning、Prompt、Key 与 Provider 错误原文不发往前端。完整 Contract
  仍在结束时校验；Forecast `CURRENT_SIGNAL_ANALYSIS` 保持缓冲，通过禁止概率检查后才输出。
- Repository 点赞和评论写入必须通过已认证用户；评论限制 2000 字符并由 Vue 纯文本插值展示，
  不执行 HTML、链接脚本或其中的指令。评论公开读取不暴露邮箱、Token 或其他用户隐私字段。
- Repository 中文本地化将 GitHub 简介和 Topic 视为 `UNTRUSTED_EXTERNAL_CONTENT`，仅作为翻译
  数据传给后端 LLM Provider；提示词明确忽略其中指令，结构化响应经长度和数量校验后才持久化。
- Repository Detail 公共请求不直接调用外部 LLM；缓存缺失仅幂等派发 Celery Task，并立即返回原文。
  API、日志和前端不接收 Provider Key，后台翻译仍执行同一不可信内容隔离与结构化响应校验。
- Redis session 有 TTL，只保存有限轮次、解析实体与约束，不保存完整 Evidence。Forecast NOT_READY
  的概率文案由生成策略和输出安全校验双重禁止。
- Copilot History 仅对认证 owner 可见，跨用户读取/删除返回404。PostgreSQL 只保存恢复问答展示所需的
  结果投影，不保存 Provider Prompt、Secret、原始 JSON 或 reasoning；删除会话同时清理 Redis context。
- Copilot 回答中的项目跳转仅使用 Backend 返回的结构化 `repository_id/full_name` 白名单并由
  Vue Router 构造站内路由；不使用 `v-html`，不把任意 LLM/RAG 文本作为可点击 URL。

- Sprint 14 Watchlist 写入仅限明确 REST 用户操作，不暴露 Agent write tool。Alert 判定只使用版本化
  确定性规则；LLM 不参与触发。Alert/Report Evidence 不包含 Secret，前端仍只访问 Backend API。
# Sprint 15 production controls

用户私有资源使用 Django User 外键与查询级所有权过滤；Agent Runtime 将 actor ID 传到 MCP/Tool Layer，Redis Session Key 包含 owner ID。Write API 仍要求用户明确操作，Agent 只读。Token 仅存于浏览器本地并通过 `Authorization: Token` 发送，不进入 Vue bundle、日志、Evidence 或文档。登录令牌采用固定有效期，默认 `AUTH_TOKEN_TTL_SECONDS=10800`（3 小时）；每次显式登录签发新令牌并重新开始计时，不采用滑动续期。后端在每个受保护请求中校验签发时间，过期令牌会被拒绝并删除；前端根据登录响应中的 `expires_at` 自动清理本地会话。旧版未记录过期时间的浏览器缓存按无效会话处理。

生产决策控制台使用 Django `is_staff` 作为服务端权限边界。普通用户不显示前端入口且管理 API 返回
403；隐藏路由本身不作为安全措施。模型激活必须精确输入 `model_version` 二次确认，并由既有
`ModelActivationService` 在事务内重新检查 VALIDATED、Dataset Gate、Validation/Test 最低指标。
控制台不提供训练、数据删除、Token 修改或自动激活能力，不返回 Artifact 路径与任何 Secret。

生产配置启用 TLS redirect、Secure Cookie、HSTS 反向代理、Host allowlist、1 MiB 请求限制和 DRF 限流。结构化日志采用字段 allowlist，拒绝记录 Headers/body/Secrets。MCP 仍为 stdio；Remote MCP 不是当前受支持的生产接口。
