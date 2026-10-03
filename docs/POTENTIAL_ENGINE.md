# Potential Engine

## V1 contract

Algorithm version: `potential-v1.0.0`.

Potential Score 是“当前可观测信号显示出的潜力”，是确定性评分，不是 Forecast Probability，
不表达未来 30 天上涨概率或成功概率。引擎只读取 PostgreSQL 中 Sprint 4 已持久化的 Trend
结果，不调用 GitHub、LLM 或机器学习模型。

## Formula

```text
BasePotential =
Trend          * 0.25
+ Momentum     * 0.20
+ TopicMomentum* 0.20
+ Community    * 0.15
+ Delivery     * 0.10
+ Novelty      * 0.10

HypePenalty = HypeRisk * 0.15
Potential = clamp(BasePotential - HypePenalty, 0, 100)
```

NULL 分量不会变成 0。`BasePotential` 对可用分量按其配置权重归一化，因此缺失值不会被当作
负面信号；缺失的原始权重和分量自身完整度会降低 confidence。

Sprint 6 没有真实 Category/Topic 历史，因此 `TopicMomentum=NULL`。当前也没有经过规范定义、
可验证的数据源来衡量 Novelty，因此 `Novelty=NULL`。两者都不以年龄、Topic 数量或常量伪造。

## Confidence

```text
base_confidence = Σ(component_weight * component_completeness)
```

- Trend 完整度使用 Sprint 4 `data_completeness`。
- Momentum、Community、Delivery 完整度读取 Sprint 4 evidence。
- Topic Momentum 和 Novelty 当前完整度为 0。
- Hype Risk 可用时 confidence 保持 base confidence；不可用时不扣 Potential 分，但
  `confidence = base_confidence * 0.85`。
- confidence clamp 到 `[0,1]`。0 与 NULL 仍是不同数据。

## Candidate rules

- `HIGH_POTENTIAL`: Potential >= 75 且 confidence >= 0.55。
- `POTENTIAL_CANDIDATE`: Potential >= 65 且 confidence >= 0.45。
- `BREAKOUT_CANDIDATE`: Potential >= 80、confidence >= 0.65、Momentum >= 75、Community >= 60、
  Delivery >= 50，且 Hype Risk 必须已有数据并且状态不是 HIGH。

High Potential Ranking 只收录 `HIGH_POTENTIAL`，依次按 Potential、confidence、Trend 降序。
Evidence 保存每个输入、权重、完整度、Hype penalty、缺失项、阈值与满足/未满足原因。
Momentum 只占 Potential 的 20%，且排名有 confidence 和多信号门槛，小项目不能仅凭高百分比
增长进入高潜榜或成为 Breakout Candidate。

## Persistence and idempotency

`repository_potential_scores` 每个 `(repository, algorithm_version)` 一行，重复计算使用 UPSERT。
保存 `potential_score`、`confidence`、`algorithm_version`、`evidence`、`calculated_at`。
Potential 仅在对应 Trend 成功持久化后计算。Evidence 不包含 Secret 或 GitHub 非结构化文本。

Sprint 6 不创建 Historical Dataset，不训练模型，也不产生 Forecast Probability。

## Star Enhanced display override

`potential-v1.0.0` 的公式、持久化结果和 Evidence 永久保留，不被机器学习模型覆盖。面向用户的
“高潜力评分”和高潜榜允许在以下条件全部满足时，自动改用 Star 增强模型输出的
`predicted_activity_percentile`（0～100）：

- Model Registry 状态为 `ACTIVE`；
- `feature_version=feature-v2.0.0`；
- Repository 存在非 NULL 的预测百分位；
- 预测归属于当前 ACTIVE Star增强模型版本；日常采集不会使该版本预测过期，只有下一模型版本人工
  激活后才切换。

不满足任一条件即回退 `potential-v1.0.0`。分类概率不得冒充百分位；原确定性 Potential 继续通过
`deterministic_potential_score` 和 Potential Evidence API 提供审计。Star 增强模型的高潜门槛为
百分位不低于80且 confidence 不低于0.45；未覆盖项目继续逐项目回退，不把 NULL 转为0。
