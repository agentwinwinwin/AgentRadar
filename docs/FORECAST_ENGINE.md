# Forecast Engine

## Forecast V1 semantic contract

Forecast V1 唯一允许的定义是：

> 未来30天进入同 Category 高开发活跃增长组的概率

它不是爆火概率、Star 上涨概率或商业成功概率。Forecast 输入只允许来自 `sample_at` 当时及之前，
`repository_id` 只用于关联，不进入 Feature。`repo_age_days` 与 `age_cohort` 继续作为模型 Feature，
但 `label-v1.2.0` 不使用 Age Cohort 进行 Label 分组。Binary Target 只由同 Category + sample_at
内的 `future_activity_percentile >= 80` 派生。

项目详情页“未来活跃增长预测”固定连接该二分类模型，主值为 `P(binary_top20_label=1)`；卡片展示
confidence、模型版本、30天周期、sample_at 和白名单 Feature Snapshot。Star 增强模型的预测百分位
只用于高潜力评分来源切换，不得进入此卡片，也不得替换 Forecast V1 的0/1概率语义。

## Training and evaluation

- Model version 前缀：`forecast-v1`。
- 比较 Logistic Regression、Random Forest、XGBoost。
- 主要切分为按 `sample_at` 排序的最早 70% Training、中间 15% Validation、最新 15% Test；
  同一时间点不能跨 Split，三个 Split 必须都含正负样本。
- 输出 Accuracy、Precision、Recall、F1、ROC-AUC、PR-AUC、Confusion Matrix。
- 模型选择依次优先 Validation PR-AUC、F1、Precision，不以 Accuracy 单独选择。
- 所有模型保存 Feature Importance、artifact SHA-256、feature/label/model version、训练时间范围、
  Dataset Gate 快照及 Validation/Test Metrics。
- `future_activity_percentile` 同时训练 Random Forest Regression baseline，报告 MAE、RMSE、R²；
  与分类模型使用相同 Time-based 边界。
- 选定分类算法使用 25%/50%/75%/100% Training 子集生成 Learning Curve；Validation PR-AUC
  或 F1 相对首点提高至少 0.05 时记录 `MORE_DATA_LIKELY_BENEFICIAL`，否则记录
  `DATASET_SIZE_CURRENTLY_SUFFICIENT`。

## Model registry and activation

Registry 状态为 `TRAINED`、`VALIDATED`、`ACTIVE`、`RETIRED`。训练完成的模型最多自动进入
`VALIDATED`，绝不自动 ACTIVE。管理员显式激活前还必须同时满足：

- Dataset Quality Gate passed；
- Validation 和独立 Test 均完整；
- Validation/Test 的 Precision、Recall、F1 均不低于 0.40；
- Validation/Test 的 PR-AUC 均不低于 0.35。

激活时会将此前 ACTIVE 模型转为 RETIRED。只有 ACTIVE 模型允许产生 Forecast；artifact 推理前必须
校验 SHA-256。

管理员无需依赖 Codex 或服务器命令：登录 AgentRadar 后，仅 `is_staff` 用户可进入生产决策控制台，
查看 Dataset Gate、Validation/Test、Feature Importance、Artifact SHA-256 与明确阻塞原因。点击激活
前必须手工输入完整 model_version；REST API 与 Service Layer 会再次验证全部门禁。前端按钮不构成
权限或指标边界，系统仍禁止自动 ACTIVE。

## Current real status

`forecast_status = NOT_READY`。真实 `label-v1.2.0` Dataset 已通过质量门禁并完成三分类模型及
Percentile Regression baseline；模型最多为 `VALIDATED`，ACTIVE 数仍为 0。API 继续返回
`forecast=null` 和 `fallback=POTENTIAL_SCORE`，等待未来明确的管理员激活决定。

当前限制：独立Test仅21条且最新07-17样本只来自Multi-Agent；Framework/Coding该日期完整Cohort
仍低于20。指标必须按小样本高方差解释，不能外推为全部AI Agent Category的稳定生产效果。
Learning Curve仍明显上升，说明未来补充数据可能有益，但本轮已按固定Early Stop停止。

管理员控制台提供持久化训练流程：Dataset Gate 与 Time-based Split 均通过且没有在途任务时，输入
`START TRAINING label-v1.2.0` 才可投递。训练只进入独立 `ml` 队列，数据库部分唯一约束与 Redis
token lock 双重防并发。状态为 `QUEUED/RUNNING/COMPLETED/FAILED/BLOCKED`；结果最多为
`VALIDATED`，必须人工激活才能上线。

ACTIVE 的 V1 开发活跃度二分类模型采用详情页按需推理：API先查询当前模型版本的持久化结果；没有
结果但存在可靠 Feature Snapshot 时，用 Redis `SET NX` 去重后投递 `forecasts.run_forecast` 到 ML
队列，并返回 `PENDING`。前端不等待推理，短暂轮询至READY；同一 Repository + Model Version 的
后续访问直接读取数据库结果。日常采集不会主动重算该预测，重新训练并激活新版本后才按新版本按需
生成。详情页不得在请求链路实时访问GitHub，也不得同步加载模型阻塞页面。

## Star enhanced percentile integration

未来 `feature-v2.0.0` Star 增强模型经过 Training、Validation、Test 和人工 Activation 后，可将其
直接预测的0～100百分位写入 `RepositoryForecast.predicted_activity_percentile`。模型由管理员人工
激活后，Celery 对所有具有可靠 `feature-v2.0.0` Feature 的 Repository 执行一次版本化批量预测。
结果固定归属于该 ACTIVE 模型版本，不因日常 Snapshot 采集而过期或漂移；只有重新训练并人工激活
下一模型版本时才重新批量预测。缺少可靠 Feature 的项目回退确定性 Potential，不伪造分数。
模型激活后新成熟的项目无需等待下一次训练：每日数据成熟度检查会将已经生成可靠
`feature-v2.0.0` 输入、但尚无当前模型结果的项目分批投递到 ML 队列，仅预测一次并按
`Repository + Model Version` 冻结。重复检查不会覆盖结果；新模型激活时才产生新版本预测。
当前 V2 数据准备未完成，因此该规则不会改变现网分数。
分类模型的高增长概率与回归/排序百分位语义不同，禁止相互换算。

首次上线门禁为真实快照跨度60天、满足跨度的Repository 200、Star增强训练样本200、有效Category
3。首次激活后采集继续，成熟度自动进入 `NEXT_RETRAINING` 周期并提高下一轮目标；达到门禁仅开放
管理员重新训练，禁止自动训练或自动激活。
