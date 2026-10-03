# Continuous Discovery & Adaptive Snapshot Monitoring

## Scope and safety boundary

Sprint 8.5 continuously discovers public AI Agent repositories and accumulates real observed
Star/Fork history. It does not backfill Star/Fork values, change Training Pool v2, activate an ML
model, produce Forecast rows, or implement Forecast V2/Sprint 9.

All GitHub calls use `GitHubClientProtocol` / `RealGitHubClient`. Credentials are read only from
`GITHUB_TOKEN`; logs and command output must never contain the token.

## Continuous discovery

Celery Beat schedules `repositories.discover_new_repositories` every 6 hours with a seven-day
`created` window, and `repositories.refresh_recent_repositories` daily with a 30-day `pushed`
window. Both reuse the complete semantic Discovery Query Pool rather than searching only “agent”.

Search results are deduplicated by GitHub repository ID. New results pass Repository Metadata and
deterministic classification, enter the confirmed Candidate Pool only, receive
`monitoring_tier=NEW`, and enqueue their first Snapshot only after transaction commit. They never
enter the Training Pool automatically.

## Adaptive monitoring

Repository monitoring state consists of `monitoring_tier`, `monitoring_enabled`,
`last_snapshot_at`, and indexed `next_snapshot_at`. Intervals are centralized in settings: HOT 3h,
NEW/RISING 6h, NORMAL 24h, STABLE 72h, DORMANT 7d and ARCHIVED 30d/disabled.

Tier decisions are deterministic and use repository age, real observed Star/Fork deltas, push
recency and archive state. Missing history produces NULL growth signals and is never converted to
zero. The hourly `snapshots.dispatch_due_snapshots` selects only due enabled rows, applies a batch
cap and Core budget check, then dispatches individual jobs. There is no per-repository Beat task.

## Snapshot and API guarantees

The existing Redis lock, transaction and `UNIQUE(repository_id, snapshot_bucket)` remain
authoritative. Snapshot rows include observed Star, Fork, subscribers, watcher alias, open issues,
pushed/updated time, archive state, completeness and `data_origin=OBSERVED`.

The production dispatcher capacity is 175 repositories per hour. It reserves the configured Core
floor and reduces the batch to the actually available Core budget instead of merely checking a
boolean threshold. Activity collection is independently tiered and Search-rate-limited; Snapshot
cadence does not imply equally expensive Activity collection for every repository.

Only elapsed OBSERVED rows may produce Star/Fork growth, velocity or acceleration. Discovery checks
Search/Core budgets and Snapshot dispatch checks Core. Safety floors pause work; transport and
Rate Limit failures use bounded Celery retry. Credentials are never logged.

## Real verification — 2026-08-17 UTC

- Before implementation: 3,079 Snapshot rows / 3,079 repositories, average 1.0, 7d=0, 30d=0.
- Bounded Discovery smoke (one query/two results): created=1, reused=1, incomplete=0.
- New repository joined Candidate v2, remained outside Training, and saved an OBSERVED Snapshot.
- Same-bucket rerun returned `created=False`; no duplicate row was created.
- Dispatcher processed exactly three NEW/NORMAL/STABLE repositories with +6h/+24h/+72h next times.
- Final: 3,084 Snapshot rows / 3,080 repositories; 7d=0 and 30d=0 remain truthful.
- Candidate v2=3,082; ACTIVE models=0; Forecast rows=0.
