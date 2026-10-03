# Production Readiness

Sprint 15 将 agentGitHub 的运行边界固定为单体 Django/DRF、Vue/Nginx、PostgreSQL/pgvector、Redis 与 Celery。生产环境必须使用 `.env.production.example` 创建独立 Secret，不得提交真实凭据。

## 上线门禁

- `DJANGO_DEBUG=false`，随机 `DJANGO_SECRET_KEY`，精确配置 `DJANGO_ALLOWED_HOSTS`。
- PostgreSQL 与 Redis 不暴露公网端口；TLS 在反向代理终止并启用 HSTS。
- Migration 是独立发布步骤：`docker compose run --rm backend python manage.py migrate --noinput`。
- `docker compose config --quiet` 是唯一允许的配置验证方式，避免解析后的 Secret 输出。
- `/api/v1/health/live` 仅表示进程存活；`/api/v1/health/ready` 检查 DB、Redis 与关键配置。
- GitHub/LLM 未配置显示 degraded，不让核心只读服务假装失败；对应采集/Agent 功能不可用。
- `/api/v1/operations/status` 仅 staff 可读，不对匿名用户暴露运维状态。

## 安全边界

Token Authentication 与 Session Authentication 均由 DRF 执行。Watchlist、Alert Receipt、Report、Copilot Session 按 Django User 隔离；公共 Repository/Trend 等只读 API 保持公开。认证、匿名、用户与 Copilot 分别限流，请求体默认最大 1 MiB。日志只记录 request/task ID、路径、状态、耗时和内部对象 ID，不记录 Header、请求正文、Token、LLM Key 或 GitHub Token。

MCP V1 保持本机 stdio。未来若提供 Remote MCP，必须另行实现 TLS、OAuth/短期 Token、租户身份绑定、逐 Tool 授权、审计、网络 allowlist 与服务级限流；不能直接暴露当前 stdio server。

## 数据真实性

Trend、Potential、Learning、Enterprise 公式和版本不变；Forecast 仅允许 ACTIVE Model 输出，当前无 ACTIVE 时保持 `NOT_READY`。Score History 从 Sprint 15 上线后开始记录真实计算结果，不回填过去时间点；Trend/Potential Change Alert 需要两个真实时间桶及既有完整度门槛。
