# Dataset Acquisition / Sampling

## Pool contract

- `sprint8-candidate-v1`：保留全部 Repository 作为 Candidate Pool，不改变网站展示、Snapshot、
  Activity、Trend 或 Potential 关系。
- `sprint8-tracked-v1`：非归档、非 Fork、未禁用且分类为 AI Agent 的项目，加上 Head Coverage
  明确命中的头部项目。
- `sprint8-training-v1`：从 Tracked Pool 以
  `(Category, Star Bucket, Age Cohort)` 分层轮询选择；分层内部使用 Activity Level 和稳定哈希，
  禁止直接按 Star 排序截断。
- Training Pool 必须为 `CONFIRMED`，Historical Backfill 管理命令才允许启动。

Star Bucket 固定为 `0-99`、`100-999`、`1K-9K`、`10K+`；NULL 单独为 `UNKNOWN`。
Age Cohort 复用 Trend Engine 的 `0-30`、`31-180`、`181-730`、`731+`。
Activity Level 根据最新 30 日 Commit + PR Created + Issue Closed 分为 HIGH/MEDIUM/LOW/INACTIVE；
没有 Activity Metric 或字段均为 NULL 时为 UNKNOWN，不转换为 0。

## 2026-08-17 coverage report

Head Coverage 前 Repository 总数为 824；对 10 个主要 Category 各检查 GitHub Star Top 10，
初始覆盖 88/100（88%），复用已有 88 个并补入缺失 12 个。所有 Search 均
`incomplete_results=false`，补入后 Repository 总数 836、Head Coverage 100/100。

### Candidate Pool 分布

| Category | 数量 |
| --- | ---: |
| OTHER_AGENT | 328 |
| AGENT_FRAMEWORK | 116 |
| MULTI_AGENT | 88 |
| CODING_AGENT | 67 |
| COMPUTER_USE | 46 |
| BROWSER_AGENT | 40 |
| AGENT_SECURITY | 34 |
| RESEARCH_AGENT | 32 |
| MCP_TOOL | 30 |
| AGENT_MEMORY | 27 |
| AGENT_OBSERVABILITY | 20 |
| AGENT_WORKFLOW | 8 |

| Star Bucket | 数量 |
| --- | ---: |
| 0-99 | 271 |
| 100-999 | 217 |
| 1K-9K | 179 |
| 10K+ | 169 |

| Age Cohort | 数量 |
| --- | ---: |
| AGE_0_30 | 8 |
| AGE_31_180 | 225 |
| AGE_181_730 | 467 |
| AGE_731_PLUS | 136 |

| Activity Level | 数量 |
| --- | ---: |
| UNKNOWN | 835 |
| MEDIUM | 1 |

主要过量区为 OTHER_AGENT，尤其其低 Star、AGE_181_730 分层；总体 AGE_181_730 也占多数。
主要不足为 AGE_0_30、AGENT_WORKFLOW，以及多个 Memory/Observability/Security/Browser/
Research 的低成员组合。Activity 覆盖严重不足，这是后续 Tracked 数据采集问题，不能用 0 填充。

Coverage Audit 只为成员少于 5 的现存组合生成 Category + Star + Created-date Query Shard；
已满足分层不生成补采查询，避免重新采集全部项目。最终有 55 个 active shard；真实小批验证执行
短缺最高的 5 个 shard、每个最多 5 条，GitHub 返回 5 条且全部已存在，因此复用 5、新增 0，
没有无意义覆盖或扩大采集。

### Head Coverage

初始已覆盖率：Framework、Browser、MCP、Observability、Security 为 100%；Multi-Agent 90%；
Memory、Coding、Computer Use 为 80%；Research 为 50%。新增 12 个真实 Repository 后全部达到
Top 10 的 100% 覆盖。已存在 Repository 只复用，未调用 UPSERT 覆盖其字段。

### Pool result

- Candidate Pool：836，CONFIRMED。
- Tracked Pool：509，CONFIRMED。
- Training Pool：300，CONFIRMED。
- Training Category：Framework 55、Multi-Agent 41、Computer Use 33、Coding 30、Browser 27、
  Security 26、Research 24、Memory 22、MCP 21、Observability 12、Workflow 8、Head OTHER 1。
- Training Star Bucket：0-99 为 90、100-999 为 80、1K-9K 为 74、10K+ 为 56。
- Training Age Cohort：0-30 为 6、31-180 为 114、181-730 为 129、731+ 为 51。

Training Pool 已通过 DRAFT Guard 验证后显式确认。本阶段没有恢复大规模 Historical Backfill；
下一次回填只能引用该 CONFIRMED Pool，并继续遵守批次、Rate Limit、Retry、BACKFILLED 和幂等规则。

## 2026-08-17 expanded-pool simulation

Discovery 扩展后 Candidate 为 3,081，按 v2 有效性规则可进入 Tracked 模拟的 Repository 为
2,622。保留并未覆盖 `sprint8-training-v2`（800）；使用同一 Category + Star + Age 分层算法
纯本地模拟 800/1,000/1,200/1,500，未创建新 Pool、未请求 GitHub。

| 规模 | Category | Cohort >=20 | Cohort >=50 | Cohort >=80 |
| ---: | ---: | ---: | ---: | ---: |
| 800 | 11 | 40 | 20 | 14 |
| 1,000 | 11 | 40 | 20 | 16 |
| 1,200 | 11 | 40 | 20 | 16 |
| 1,500 | 11 | 40 | 20 | 16 |

以上 Cohort 总数按 11 Category × 4 个统一 sample_at 统计。扩大规模主要增加 Framework、Coding、
MCP、Multi-Agent；Memory、Observability、Security、Workflow、Browser、Research 已受 Candidate
供给上限约束，因此 1,000 以后并未增加达到 50/80 的 Cohort 数。不能靠机械扩大 Pool 解决这些
Category 的覆盖不足。

逐规模最终 Category 分布：

- 800：Framework 180、Memory 41、Observability 24、Security 39、Workflow 19、Browser 41、
  Coding 132、Computer 65、MCP 90、Multi 130、Research 39。
- 1,000：256、41、25、39、19、43、163、71、121、183、39。
- 1,200：361、41、25、39、19、43、186、71、155、221、39。
- 1,500：584、41、25、39、19、43、215、71、194、230、39。

完整逐 `sample_at` Cohort 数由 `evaluate_dataset_design` 管理命令可重复生成；该命令只读 Pool
候选并复用现有 Bucket，不进行 Discovery 或 Backfill。

## 2026-08-17 targeted historical completion

最终决策保留 Candidate 3,081 和 CONFIRMED Training Pool v2 800，不扩大Pool。仅对
Framework、Multi-Agent、Coding运行两批Targeted Backfill，并在Dataset Early Stop后停止。

| Category | 04-18 | 05-18 | 06-17 | 07-17 |
| --- | ---: | ---: | ---: | ---: |
| Framework Label Complete | 26 | 26 | 26 | 17 |
| Framework Percentile Samples | 26 | 26 | 26 | 0 |
| Multi-Agent Label Complete | 28 | 28 | 28 | 21 |
| Multi-Agent Percentile Samples | 28 | 28 | 28 | 21 |
| Coding Label Complete | 24 | 24 | 24 | 16 |
| Coding Percentile Samples | 24 | 24 | 24 | 0 |

07-17只有Multi-Agent单类达到20，但全Dataset已经有255样本、4个sample_at、90天跨度，且
time-based Train/Validation/Test三段都有正负样本，因此按Early Stop停止，没有为30～35或50
继续消耗API。两批新增396 Bucket，总Bucket=1,142；API合计1,626，其中Search=1,465、Core=161。
