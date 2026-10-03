# Operations Runbook

## 日常观测

- `/api/v1/health/live`：进程 liveness。
- `/api/v1/health/ready`：PostgreSQL、Redis、生产配置 readiness；GitHub/LLM 仅作 degraded 标记。
- `/api/v1/operations/status`：staff 可见依赖状态和最近 Snapshot/Activity 时间。
- JSON 日志通过 `X-Request-ID`、Celery `task_id` 关联。Celery输出 started/completed/retry/failed 和耗时。
- 建议平台基于 5xx、p95 延迟、Celery failure/retry、队列积压、GitHub remaining、数据 freshness 告警。

## 故障处理

- DB/Redis readiness 失败：从负载均衡摘除 Backend，停止 Beat 派发，确认依赖后恢复。
- GitHub 限流：保留 checkpoint，遵循已有 remaining/reset/backoff，不放大并发。
- LLM 故障：Copilot 返回明确错误；结构化 Dashboard、评分和 Alert 不受影响。
- Celery failed/retry：按 task_id 查结构化日志。任务保持幂等，修复根因后可重放；禁止直接改业务表。
- `scoring` 异常积压：先按任务名统计 Redis List，不得直接清空。正常链路同仓库15分钟内由
  `agentradar:celery:pending:{purpose}:{repository_id}` 合并；`celery-scoring` 独立消费
  `operations,scoring`。历史重复消息需要整理时，先执行 Redis `BGSAVE`，停止 Beat/相关 Worker，
  保存任务类型统计，再只移除确认可由数据库状态重建的评分消息并补发成熟度检查与过期评分。
  全量 Alert 兜底在 `scoring` 超过1,000项时返回 `SKIPPED_BACKLOG`，并使用23小时全局派发键，
  防止历史 Beat 消息或重复调度再次成倍放大队列。
- 用户详情翻译由 `celery-interactive` 独立消费 `interactive`；GitHub采集由 `celery-worker` 消费，
  评分与运维检查由 `celery-scoring` 消费。排障时分别检查，禁止跨队列混用 Worker。
- Compose 重建 Backend 或 Frontend 后必须执行 `docker compose ... restart reverse-proxy`，使 Nginx
  重新解析容器地址；随后同时验证 readiness 和一个真实项目详情。跳过该步骤可能因旧容器 IP 出现
  502，而 Backend 本身仍正常。
- Score Change 未触发：先确认存在两个上线后真实 `repository_score_history` 时间桶，不补造历史。

## Retention

默认 Alert/Report 保留365天、Watchlist Event保留730天；Redis Copilot Session 继续依赖 TTL，Celery Result保留24小时。`python manage.py enforce_retention` 默认只报告；`--apply` 才删除过期行。生产 Beat 每日执行同一策略。Snapshot、Activity、Training Dataset、Model Registry、Knowledge 与 Score History 不在本次自动删除范围内，变更需单独数据治理评审。

## GitHub 与磁盘容量基线（2026-08-18）

- 腾讯云主机认证额度实测：Core 5,000/小时、Search 30/分钟；`/rate_limit` 往返约0.20秒。
- 动态监控分层生产模拟约195次Snapshot/小时；每小时225的派发上限覆盖当前稳态并保留余量。
- 动态降频需满足60天OBSERVED Snapshot跨度；保护期内最低NORMAL，BACKFILLED Snapshot不计入跨度。
- Snapshot间隔：HOT 6小时、RISING 12小时、NEW（前7天）12小时、NORMAL/Training每日、
  STABLE 72小时、DORMANT 168小时。每日训练桶不会因产品监控频率不同而增加样本权重。
  Dispatcher仍受Core剩余额度保护，项目继续增长时不会突破有界批次。Activity按Monitoring Tier
  到期派发并限速1个Repository/分钟；
  首次2个/分钟真实验收触发Search限流后已收紧，Retry按GitHub reset时间执行。
- 系统盘59GB，当前使用8.3GB（15%），剩余49GB；PostgreSQL Docker Volume约225MB，Redis约80KB。
- 所有 Compose 服务使用 `json-file` 10MB × 3轮转，防止容器日志无限增长。禁止自动清理 Volume。
- 可安全定期删除的是未引用 Docker Image 与过期 Build Cache；不得自动删除 Snapshot、Activity、
  Training Dataset、Model Registry 或用户数据。磁盘达到70%先清理可重建缓存，达到80%告警并做
  表级容量审计，禁止以“腾空间”为由直接删业务历史。
