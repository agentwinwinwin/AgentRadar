# Repository Knowledge Base & RAG V1

## Boundary

RAG stores only unstructured repository knowledge: README, selected Markdown docs, recent Release
notes, deterministic high-value merged PRs and Issues. Star/Fork/Snapshot/Trend/Potential/Forecast
and activity counts remain authoritative structured PostgreSQL data and are never answered from
embeddings. All GitHub text is `UNTRUSTED_EXTERNAL_CONTENT` and cannot become instructions.

## Source policy

Allowed source types are README, DOC, ARCHITECTURE, DESIGN, SECURITY, CONTRIBUTING, RELEASE,
PULL_REQUEST and ISSUE. V1 reads `docs/**/*.md` to depth two with a global budget of 25 core docs
per repository, named root design/install/deployment documents, and the latest five non-draft
Releases. It excludes source trees, lock/build/vendor/generated/binary content and caps text files
at 500 KB. PR/Issue collection is disabled for routine Pilot sync and enabled only for explicitly
selected Smoke repositories.

PR selection is deterministic: recent 90-day merged items with feature/architecture/refactor/
runtime/memory/agent/tool/MCP/workflow/security/performance/breaking signals or material discussion;
typo/format/dependabot/dependency bump/minor docs/chore are excluded. Issue selection prioritizes
bug/security/performance/architecture/breaking/major-feature or material discussion and excludes
duplicates and low-value automation. Selection evidence is persisted in Document metadata.

## Document and change detection

Document identity is `(repository, source_type, external_id)`. SHA-256 `content_hash` prevents
unchanged re-embedding. Changed content increments `document_version`, replaces current chunks and
embeds the new content. Removed sources become inactive. Fetch time, source URL, GitHub timestamps
and untrusted-content metadata remain traceable.

## Chunk policy

Markdown chunking is heading-aware and preserves fenced code, lists and tables as semantic blocks.
Target size is 400–800 approximate tokens (600 target) with about 75-token overlap. Every chunk
stores heading path, token count, content hash, document version and repository identity.

## Embedding V1

`EmbeddingClient` is the provider boundary. V1 uses configurable `local_hashing` model
`hashing-384`, `embedding-v1.0.0`, producing normalized 384-dimensional vectors without sending
untrusted repository text to an external provider. This is a deterministic lexical baseline, not a
general semantic model. Model and version are stored per chunk so a future provider can re-embed
under a new version without silently changing semantics.

## Retrieval policy

Repository questions must filter `repository_id` before pgvector cosine search. Cross-repository
research may filter Category, source type and GitHub update time. Temporal questions can apply
update-time filters. Evidence returns repository, source type, title, path, URL, snippet, similarity
score and updated time. V1 retrieves pgvector cosine candidates and applies a small deterministic
metadata/source-intent rerank; the returned Evidence score remains the original cosine similarity.

`RAGService` returns an extractive evidence-grounded answer for validation. It does not invoke an
LLM or implement PM Copilot. `structured_and_rag` demonstrates that numeric facts come from domain
tables while narrative evidence comes from Knowledge retrieval.

## Scheduling and cost

Knowledge sync uses the `knowledge` Celery queue, Redis repository lock, bounded retry and a daily
dispatcher restricted to repositories already admitted to the Pilot through `KnowledgeSyncState`.
It cannot automatically expand to the full Tracked Pool. Refresh intervals are tier-aware: HOT/RISING
daily, NEW every three days, NORMAL every three days, STABLE weekly and DORMANT monthly. Each run
records repositories, documents, chunks, approximate tokens, embedding calls, changed/unchanged
documents and GitHub calls.

## Known limitations

- Local hashing primarily matches lexical concepts and synonyms less reliably than a trained
  semantic embedding model.
- GitHub Search indexing and the bounded PR/Issue candidate page can omit relevant discussions.
- V1 answer composition is extractive; natural-language synthesis belongs to a future provider and
  must remain evidence constrained.

## 50-repository Pilot result

- 50 repositories contain active Knowledge documents; expansion stopped at the lower Pilot bound.
- 302 active documents and about 1,500 active chunks contain about 0.89M approximate tokens,
  averaging about 17.7K tokens per repository.
- Source mix is approximately README 16.6%, core docs 75.5%, and Release 5.0%; two selected PRs and
  seven selected Issues are retained only for Smoke validation.
- Real pgvector retrieval covered positioning, architecture, installation, Agent/MCP capability,
  Release changes and security/engineering risk. Repository filtering and every required Evidence
  field were verified.
- Immediate unchanged resync produced `changed_documents=0`, `embedding_calls=0` and
  `skipped_unchanged=5`.
- API accounting added during the Pilot records 449 calls in latest per-repository states and zero
  Search calls for routine batches. This is a conservative lower bound because the initial seven
  Smoke repositories and one safely interrupted pre-budget traversal predated cumulative accounting.
