# Repository Domain

## Sprint 1 scope

Sprint 1 establishes the current-state Repository domain only:

- `Repository` stores verified GitHub repository metadata.
- `RepositoryCategory` is the fixed V1 category enumeration from the master specification.
- `Topic` and `RepositoryTopic` store normalized GitHub topic relationships.
- `GitHubDiscoveryQuery` is the administrator-editable discovery query pool.
- `RepositoryService` performs transactional, idempotent create/update by GitHub numeric ID.
- `RepositoryDiscoveryService` searches configured queries and delegates persistence to
  `RepositoryService`.

Snapshot, activity metrics, contributors, releases, scoring and Celery collection are not part of
Sprint 1.

## Category rules

The V1 classifier uses verified GitHub `topics` and `description`. Rules are deterministic and run
only when a Repository is first created. Subsequent synchronization preserves the stored category,
so an administrator can override it in Django Admin without the next sync undoing that decision.

Categories:

`AGENT_FRAMEWORK`, `CODING_AGENT`, `BROWSER_AGENT`, `RESEARCH_AGENT`, `MULTI_AGENT`,
`AGENT_MEMORY`, `AGENT_WORKFLOW`, `MCP_TOOL`, `COMPUTER_USE`, `AGENT_OBSERVABILITY`,
`AGENT_SECURITY`, `OTHER_AGENT`.

## Identity and idempotency

- GitHub numeric `id` maps to unique `repositories.github_id` and is the update identity.
- `full_name` remains unique but may change when a repository is transferred or renamed.
- Topic links are protected by `UNIQUE(repository_id, topic_id)`.
- Repeating discovery or single-repository sync updates the existing row.
- GitHub null values remain database NULL; they are not converted to zero or empty strings.
