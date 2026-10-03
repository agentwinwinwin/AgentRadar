# Repository Snapshot Pipeline

## Sprint 2 scope

Sprint 2 observes current Repository counters and creates durable six-hour UTC snapshots. It does
not calculate activity metrics, growth, Trend Score or any Sprint 3+ output.

## Data flow

```text
Celery Beat (every 6 hours)
  -> snapshots.capture_due_repository_snapshots
  -> snapshots.create_repository_snapshot(repository_id)
  -> Redis SET NX EX lock
  -> GitHubClient.get_repository
  -> database transaction
       Repository current-state update
       RepositorySnapshot UPSERT
     commit
  -> transaction.on_commit
  -> snapshots.snapshot_persisted
```

GitHub HTTP remains confined to `RealGitHubClient`; tests use `FakeGitHubClient`.

## Time bucket

The default bucket is six hours in UTC. `2026-08-16T06` represents
`[2026-08-16 06:00, 2026-08-16 12:00)` UTC. The bucket function rejects naive datetimes and invalid
bucket sizes.

## Idempotency and concurrency

- Service writes use `update_or_create(repository, snapshot_bucket)`.
- PostgreSQL enforces `UNIQUE(repository_id, snapshot_bucket)`.
- Repository tasks acquire `agentGitHub:github:repo:{repository_id}` with Redis `SET NX EX`.
- Locks have a 300-second TTL and use token-checked Lua release, so an expired lock cannot delete a
  newer worker's lock.
- Lock contention, GitHub client errors and database errors use bounded Celery retry.
- Follow-up work is registered with `transaction.on_commit`; rollback cannot publish it.

## NULL and completeness

Snapshot counters and `github_pushed_at` are nullable. Missing GitHub values remain NULL and are
never converted to zero. `data_completeness` is the fraction of the five observed Snapshot fields
that are non-null and is protected by a database check constraint in `[0, 1]`.

## Scheduling and queues

Beat dispatches every six hours to `github_normal`. The Compose worker consumes both `celery` and
`github_normal`. Archived and disabled repositories are not dispatched.
