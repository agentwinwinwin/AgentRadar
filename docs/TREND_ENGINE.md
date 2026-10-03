# Trend Engine

## V1 contract

Algorithm version: `trend-v1.0.0`.

The engine is deterministic Python. It reads Repository, Snapshot and Activity rows from
PostgreSQL. It never calls GitHub or an LLM. All scores are clamped to `[0, 100]`; source NULL is
never converted to zero.

## Cohort and percentile

Age cohorts use age at calculation date:

- `AGE_0_30`: 0–30 days
- `AGE_31_180`: 31–180 days
- `AGE_181_730`: 181–730 days
- `AGE_731_PLUS`: 731+ days

The comparison cohort is `(repository.category, age_cohort)`. NULL observations are excluded.
Percentile uses tie-aware average rank: `(average_rank - 1) / (n - 1) * 100`. A one-member cohort
returns 50. This makes results independent of database row order.

## Components

Component scores use a weighted mean of available inputs. Missing inputs are omitted and reduce
component and overall completeness; they are not scored as zero.

- Momentum: star delta 7d 25%, star growth 7d 15%, fork delta 7d 10%, star delta 30d 20%, star
  growth 30d 10%, fork delta 30d 10%, star acceleration 10%. Relative growth denominators use
  `max(previous_value, 10)` to prevent tiny bases from dominating.
- Development: commits 30d percentile 30%, PR created 30d percentile 20%, PR merged 30d
  percentile 20%, active contributors 30d percentile 30%.
- Community: issues closed 30d percentile 25%, close ratio 25%, PR participation percentile 20%,
  active contributors percentile 15%, Community Health 15%. Close ratio is available only when
  opened and closed counts are both present; `opened=closed=0` is a real 100 (no unresolved
  inflow), not missing data.
- Delivery: releases 30d percentile 45%, releases 90d percentile 25%, release recency 30%. Recency
  declines linearly from 100 today to 0 at 90 days.
- Adoption: current stars percentile 65%, current forks percentile 35%.
- Topic Momentum: NULL in V1 because no historical Category/Topic Snapshot exists. It is not
  fabricated from current repository metrics.
- Maintenance: archived repositories score 0. Otherwise push recency 35%, release recency 20%,
  Community Health 25%, contributor diversity 20%. Push recency reaches 0 at 90 days; release
  recency reaches 0 at 180 days. Contributor diversity is `1 - top_contributor/total`.

Trend uses the master weights:

```text
Momentum 25%, Development 20%, Community 15%, Delivery 10%, Adoption 10%,
Topic Momentum 10%, Maintenance 10%
```

Unavailable components are omitted from the numeric weighted mean and reduce
`data_completeness` by their configured weight. Therefore V1 completeness cannot exceed 0.90
until genuine Topic Momentum history exists.

## Snapshot history

The latest snapshot on or before the calculation date is the current observation. A 7d/30d
feature requires a snapshot at least 7/30 days older. Missing history produces NULL feature values
and lower completeness. Negative deltas caused by unstars/unforks remain valid observations.

Acceleration is recent 7-day star velocity minus the preceding 23-day velocity.

## Hype Risk

Hype Risk is calculated only when 30-day star and fork histories are available and both Development
and Community components have 100% input completeness. Otherwise score is NULL and status is
`INSUFFICIENT_HISTORY`.

```text
gap = star_growth_30d_percentile
      - mean(fork_delta_30d_percentile, Development, Community)
hype_risk = clamp(gap, 0, 100)
```

Statuses: 0–30 `LOW`, >30–60 `MEDIUM`, >60 `HIGH`.

## Lifecycle

Rules are evaluated in order:

1. archived or Maintenance < 20 → `DORMANT`
2. Trend >= 88, Momentum >= 88, Development >= 70 and Hype Risk <= 40 → `BREAKOUT`
3. Trend >= 75 and Momentum >= 80 → `ACCELERATING`
4. repository age < 180 and Trend >= 65 → `EMERGING`
5. Trend >= 60 → `GROWING`
6. Trend < 45 and Momentum < 40 → `COOLING`
7. otherwise → `MATURE`

If Trend cannot be calculated, lifecycle is `DORMANT` only for archived repositories and otherwise
`MATURE`; evidence records the missing inputs.

## Evidence and persistence

`repository_trend_scores` stores one row per `(repository, algorithm_version)`. Recalculation is an
UPSERT. Evidence contains calculation date, cohort, cohort sizes, raw features, percentiles,
component completeness, missing inputs, formula weights and Hype/Lifecycle reasons. It contains no
secret or untrusted GitHub text.
