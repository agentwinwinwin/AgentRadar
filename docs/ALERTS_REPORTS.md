# Watchlist、Alert 与 Scheduled Report

## 版本

- Alert Rule：`alerts-v1.0.0`
- Report Rule：`reports-v1.0.0`

## Watchlist

V1 使用后端 owner key 隔离默认列表；添加和取消必须由明确的写 API 发起。读取 Tool 不会创建或修改
Watchlist。Watchlist 与 Candidate、Tracked、Training Pool 完全独立。

## Alert 规则

所有阈值集中定义于 `apps.watchlists.rules.AlertThresholds`。Alert 只读取已有结构化数据并确定性判断，
唯一约束 `(repository, alert_type, rule_version, event_bucket)` 提供最终幂等保护。

| 类型 | V1 数据与门禁 |
| --- | --- |
| STAR_GROWTH_SPIKE | 完整度 >=0.8 且有真实 >=7d Snapshot baseline；绝对与相对增长同时过阈值 |
| FORK_GROWTH_SPIKE | 同上，Fork 使用独立阈值 |
| ACTIVITY_SURGE | 当前与 >=7d Activity baseline 均非 NULL |
| NEW_RELEASE | 非 Draft、最近30天的真实 Release；按 GitHub Release ID 去重 |
| PROJECT_DORMANT | Activity `days_since_last_push`，缺失时使用真实 `github_pushed_at` |
| NEW_HIGH_POTENTIAL_PROJECT | Potential >=80、confidence >=0.45、Trend completeness >=0.5 |
| TREND_CHANGE | 保留类型；当前单版本当前态表无可靠时间序列，V1不伪造触发 |
| POTENTIAL_CHANGE | 保留类型；当前单版本当前态表无可靠时间序列，V1不伪造触发 |

任何 NULL、`INSUFFICIENT_HISTORY` 或不满足完整度/置信度的输入都不会被当作 0，也不会产生强提醒。

## Scheduled Report

日报按已结束 UTC 自然日、周报按已结束 UTC 周生成，固定时间桶和版本唯一约束保证幂等。内容来自
Repository、Watchlist Event 与 Alert Evidence，包含新项目、关注变化、Trend/Potential/Release/Activity
变化和证据不足项。`llm_used=false`；Sprint 14 不让 LLM 重算事实或评分。

## Celery

- `alerts.dispatch_alert_evaluation`
- `alerts.evaluate_repository_alerts`
- `reports.generate_daily_report`
- `reports.generate_weekly_report`

Snapshot、Activity、Trend、Potential 成功持久化后可派发单仓库评估。Beat 复用现有 Worker，重复任务由
Service 与数据库唯一约束共同保证幂等。

## Sprint 15 score history

Trend/Potential Change 从 `repository_score_history` 的两个真实6小时时间桶比较。部署前没有真实记录时
保持不触发；禁止为启用规则补造历史。Alert 事实全局唯一，用户 `UNREAD/READ/DISMISSED` 状态保存在
`alert_receipts`，用户之间互不影响。
