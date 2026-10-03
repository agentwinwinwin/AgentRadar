# Historical Dataset

## V1 contract

- Feature version: `feature-v1.0.0`
- Current training Label version: `label-v1.2.0`
- Preserved binary Label version: `label-v1.1.0`
- Preserved legacy Label version: `label-v1.0.0`
- Historical acquisition version: `activity-bucket-v1.0.0`
- Sampling version: `monthly-sampling-v1.0.0`
- Dataset 只用于构造训练样本；Sprint 7 不训练模型，不产生 Forecast Probability。
- 每个样本站在 UTC 历史时间点 `sample_at=T`。

## Windows and provenance

- 7 日 Feature 窗口：`T-6` 至 `T`，闭区间。
- 30 日 Feature 窗口：`T-29` 至 `T`，闭区间。
- 30 日 Label 窗口：`T+1` 至 `T+30`，闭区间。
- Feature 来源时间必须 `<= T`；Label 来源时间必须 `> T`。
- GitHub Search 回填窗口写入 `historical_activity_windows`，并标记
  `data_origin=BACKFILLED`。系统实时 Snapshot 不被修改，也不冒充为回填 Star 历史。

只有 Label 窗口已经完整结束的样本点才能构建。GitHub Search
`incomplete_results=true` 对应值保存 NULL；NULL 不转换成 0。

## Feature V1

保存总规范字段：

- `repo_age_days`、`category`
- `current_stars`、`current_forks`
- `commit_7d`、`commit_30d`
- `pr_created_7d`、`pr_created_30d`、`pr_merged_30d`
- `issue_created_30d`、`issue_closed_30d`
- `active_contributors_30d`、`release_count_30d`
- `days_since_last_push`、`days_since_last_release`
- `community_health`、`topic_momentum`

历史 Star/Fork 只允许读取 `snapshot_at <= T` 的本系统 OBSERVED Snapshot；没有则为 NULL。
历史 Push、Community Health 没有可靠历史快照时为 NULL。Topic Momentum 仍因无历史 Category
Snapshot 为 NULL。Feature provenance 记录每个来源窗口和最大来源时间。

## Label V1

Label 窗口内使用五个可回溯活动信号：

- Commit Activity：commit count
- PR Activity：created + merged
- Contributor Activity：Contributor Statistics 周数据中的活跃贡献者
- Release Activity：published release count
- Issue Resolution Activity：closed issue count

`label-v1.1.0` 在同一个 `sample_at` 的 `category` 内使用 tie-aware average-rank Percentile，
五项等权计算
`FutureActivityGrowthScore`。五项任一 NULL 时不创建该 Training Sample，不能将不完整标签当负样本。
`label_score >= 80` 为 `label=1`，其他为 `label=0`。正式 Dataset 的 Label Cohort 最少需要
20 个完整候选，由 `DATASET_MIN_LABEL_COHORT_SIZE` 配置；不足时不产生 Label 或 Training
Sample，已有同版本小 Cohort 样本会在 Builder 重跑时删除。单元测试通过显式参数使用 5 人门槛，
不得影响正式训练配置。

`label-v1.0.0` 使用 `(category, age_cohort, sample_at)`，因当前 Training Pool 下过度分层而保留为
只读兼容版本，不覆盖、不删除。`label-v1.1.0` 从 Label 分组键移除 Age Cohort，但
`repo_age_days` 与 `age_cohort` 继续作为模型 Feature，年龄信息没有删除。

### Label v1.2.0 percentile target

`label-v1.2.0` 保留 `label-v1.1.0` 的 `(category, sample_at)` Cohort、五项真实 Activity
信号、等权综合和正式最小 Cohort 20。它将同一份未来 30 日数据显式保存为：

- `future_activity_percentile`：0～100 的 Cohort 内综合表现 Percentile；
- `binary_top20_label`：只由 `future_activity_percentile >= 80` 派生；
- `label_cohort_size`：生成 Target 时的完整候选数量。

Cohort 小于 20 或五项信号任一为 NULL 时，不创建该版本 Training Sample，因此两个 Target
均保持不可用，不能写成 0。`label-v1.0.0`、`label-v1.1.0` 不覆盖、不删除；兼容字段
`label`/`label_score` 在 v1.2 分别与 binary/percentile 保持相同值。Sprint 8 真实训练显式使用
v1.2；旧版本不覆盖、不删除。

## Idempotency and leakage guard

`training_samples` 唯一键为
`(repository, sample_at, feature_version, label_version)`，重复 Builder 使用 UPSERT。
同一 Repository 可在不同 `sample_at` 生成多条样本。

Builder 在持久化前执行自动化时间审计：Feature window end、Snapshot、Trend 等来源不得晚于 T；
Label window start 必须晚于 T。`repository_id` 仅作关联键，禁止写入 features。

## Dataset quality

质量报告输出：总样本、正负样本数量及比例、Category/Age Cohort/sample_at 分布、样本时间范围、
逐 Feature 缺失数量与缺失率、Feature/Label version 分布。报告只统计已持久化样本。

## Large historical backfill

- 真实项目按持久化 Batch/Item 分批执行；每个 `(batch, repository, sample_date)` 唯一，成功项在
  重跑时跳过，失败项在最大尝试次数内可断点续跑。
- `monthly-sampling-v1.0.0` 默认只覆盖最近 6～12 个月，`sample_at` 使用精确 30 天间隔；
  Feature/Label 时间窗口语义不变。旧的 14 天批次标记为 legacy/partial，
  已写数据保留但不继续扩大。
- Contributor Statistics 与 Release 在同一仓库批次中复用；Search、Contributor Statistics、
  Release 请求量和限额等待次数均写入批次检查点。Contributor 周数据未完整覆盖窗口时保存 NULL，
  不把缺失数据写为 0。
- 大规模回填只允许引用 `CONFIRMED` 的 TRAINING Repository Pool。Candidate/Tracked/Training
  的采集、覆盖和分层规则见 `docs/DATASET_ACQUISITION.md`；Training 不得按 Star 简单截断。

## Materialized historical activity buckets

`activity-bucket-v1.0.0` 先写入 PostgreSQL 基础桶，再由本地数据物化现有
`historical_activity_windows`：

- 每个 sample 的 30 日 Feature 桶与上一个 sample 的 30 日 Label 桶完全复用；N 个 sample
  只需要 N+1 个连续、互不重叠的精确 30 日 Activity 桶。
- 30 日桶调用 Commit、PR Created/Merged、Issue Created/Closed 五个 Search。
- 每个 sample 只额外采集精确 7 日尾桶的 Commit 与 PR Created 两个 Search。
- Contributor Statistics 每仓库获取一次，按 contributor/week 持久化到
  `historical_contributor_weeks`；多个窗口本地计算 active contributors。
- Release published date 每仓库获取一次并保存在 source cache，多个窗口本地聚合。
- Bucket 与 Window 均标记 BACKFILLED，保存 acquisition version；不生成历史 Star/Fork。
- Bucket 唯一约束使中断后重跑直接复用已成功桶，不再次调用 GitHub。

请求估算（Contributor Stats/Release 各按一次计算）：

| 月度 sample 数 | 旧方案/仓库 | Bucket/仓库 | 100 仓库旧→新 | 候选 Sample | 降幅 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 92 | 49 | 9,200→4,900 | 600 | 46.74% |
| 10 | 152 | 77 | 15,200→7,700 | 1,000 | 49.34% |
| 12 | 182 | 91 | 18,200→9,100 | 1,200 | 50.00% |

每批物化和 Dataset Builder 完成后运行 Early Stop：必须同时满足 Dataset Quality Gate，且
time-based Training/Validation/Test 三段均同时存在正负样本，才允许停止后续补采并进入真实训练。

## Sprint 8 quality gate

训练前必须通过以下固定门禁：总样本不少于 200、正样本不少于 20、负样本不少于 80、正样本比例
在 5%～45%、至少 2 个 Category、至少 2 个 Age Cohort、任一 Feature 缺失率不超过 60%、
时间跨度不少于 90 天、至少 3 个不同 sample_at，当前训练只允许使用
`feature-v1.0.0` / `label-v1.2.0`。
门禁报告必须完整保留实际值和阈值；失败时禁止训练。
