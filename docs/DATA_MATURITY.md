# Data Maturity / Capability Auto Activation

本机制属于 V1 运行能力增强，不是新业务 Sprint。它只根据真实持久化数据决定能力是否可用，
不修改 Trend、Potential、Forecast V1、Dataset 或 Model Registry。

## 状态

- `ACCUMULATING`：尚未满足数据门禁，权威数值继续为 NULL。
- `READY`：满足真实覆盖门禁，可以计算或展示。
- `DEGRADED`：曾经 READY，但当前覆盖跌破门禁。
- `DISABLED`：运维显式停用，自动评估不会覆盖。

每项状态保存 `data_coverage`、`data_as_of`、`first_ready_at`、
`last_evaluated_at`、`reason`、`algorithm_version` 和可审计 metrics。

## 门禁

Star/Fork 7d、30d 只使用 `data_origin=OBSERVED` 且完整度至少 0.8 的 Snapshot；
BACKFILLED 数据永远不能令这些能力 READY。基线容许最多 2 天采集时间误差，且对应字段必须非 NULL。
全局默认要求至少 20 个有效 Repository、覆盖率至少 50%。

Momentum 依赖 Star/Fork 7d、30d 与完整 Activity；Hype Risk 依赖 Star/Fork 30d 与完整 Activity。
数据不足时维持 ACCUMULATING，现有评分的 NULL 语义不变。

`CATEGORY_TREND` 使用 `category-trend-v1.0.0`。默认每个 Category 至少 20 个有效 Repository、
覆盖率至少 60%，并至少有 2 个可比较 Category。它复用现有 Trend Score，不改变 Trend 公式。
不足时 Dashboard 使用 `CATEGORY_DISTRIBUTION`；READY 后同一前端按 API 状态自动显示分类趋势。

Trend/Potential Change Alert 要求至少两个真实 Score History 时间桶。Forecast V2 仅计算
`FORECAST_V2_DATA_READINESS`：默认要求 200 个具有 60 天 OBSERVED Snapshot 的 Repository、
200 个有效 `feature-v2.0.0` / `label-v2.0.0` Star增强 Training Sample 和至少 3 个 Category。
Feature需要60天真实历史，Label还需要之后30天真实活动，因此首批样本理论上至少积累90天。READY不训练、不激活、
不替换 Forecast V1，仍须 Training → Validation → Test → VALIDATED → 人工 Activation。
以上是首次上线门禁。首次 Star增强模型人工激活后，能力自动进入 `NEXT_RETRAINING` 积累周期并保存
更高的下一轮目标；Snapshot采集继续，但不会自动训练、自动激活或改变当前模型版本的项目预测。

## 调度与自动重算

Celery Beat 每日调用 `capabilities.evaluate_data_maturity`。任务使用 Redis 全局锁，状态 UPSERT 幂等。
当 Growth、Momentum 或 Hype 首次转为 READY 时，仅派发一次分页重算；每批默认 200 个 Repository，
批次间隔 5 秒。重算复用既有链路：Trend → Potential → Score History → Alert Evaluation。
重复评估不会重复触发首次 READY 重算。

可通过环境变量调整部署规模门槛和 `CAPABILITY_RECALC_BATCH_SIZE`，但不得以配置伪造 READY。
