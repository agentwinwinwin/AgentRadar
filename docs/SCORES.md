# Learning / Enterprise Score

Sprint 10 adds two deterministic, versioned Repository assessments. Neither score calls an LLM or
GitHub during calculation; both consume only persisted Repository, Trend, Activity and Knowledge
metadata.

## Learning Score (`learning-v1.0.0`)

Weights: Documentation 20, Architecture 20, Code Structure 15, Examples 15, Testing 10,
Community 10, Maintenance 10. Code Structure remains NULL until a verified directory-structure
source exists. Missing components are excluded from the weighted denominator and reduce
`confidence`; they are never converted to zero.

## Enterprise Score (`enterprise-v1.0.0`)

Weights: License 15, Documentation 10, Release Stability 10, Maintenance 15, Community 10,
Testing 10, Security 10, Deployment 10, Integration 5, Ecosystem 5. A known Hype Risk applies the
documented deterministic penalty. Recommendations are `ADOPT`, `POC`, `WATCH`, or `AVOID`.

## Evidence and ranking

Each component records `VALUE`, `MISSING`, or `INSUFFICIENT_HISTORY`, its value and weight. Knowledge
state is explicit: `NOT_INGESTED` means the pilot has not processed the repository;
`DOCUMENT_NOT_FOUND` means ingestion completed but no eligible document exists. These states are
not interchangeable.

Discover ranking uses persisted scores and excludes rows below configurable confidence thresholds
(`LEARNING_RANKING_MIN_CONFIDENCE`, `ENTERPRISE_RANKING_MIN_CONFIDENCE`, default `0.60`). Low-confidence
detail remains visible as “数据积累中 / 数据不足”; the UI never presents NULL as zero.

## V1 full-repository scoring (`learning-v1.1.0` / `enterprise-v1.1.0`)

V1.1 removes RAG as a scoring prerequisite. It reuses persisted Repository current state, Activity,
Trend, Contributor, Release and License data. A bounded optional enrichment checks only the root,
`docs/`, and `.github/` filename/path metadata through `GitHubClient`; it never downloads a full tree,
source corpus, or embeddings. `NOT_INGESTED` remains unknown and is not treated as file absence.

Learning weights are Development Activity 25, Documentation 25, Architecture/Learning 20,
Community 15, Delivery 10 and Maintenance 5. Enterprise weights are Maintenance 20, Community 15,
Delivery 15, Security 15, License 10, Documentation 10, Architecture/Operations 10 and Risk 5.
Missing dimensions are excluded from the denominator and reduce confidence. Old v1.0 rows remain
unchanged; `(repository, algorithm_version)` provides versioned UPSERT.

The batch pipeline uses bounded resumable dispatchers, per-repository Redis locks and finite retries.
New Repository discovery, Knowledge completion and Trend maturation trigger recalculation. Activity,
Contributor and Release updates flow through the existing Activity → Trend trigger to avoid duplicate
task storms. Daily lightweight enrichment is rate-budgeted and only selects repositories without a
persisted assessment evidence record.
