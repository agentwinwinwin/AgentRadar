# Skill Engine & Workflow Policy V1

Sprint 12 Skills are AgentRadar runtime business policies, not Codex Skills and not an Agent. They
define when and in what order the read-only Sprint 11 Tools may be called. Skills do not access ORM,
SQL, GitHub, embeddings or scoring engines.

## Contract and loading

Each `skills/*/SKILL.md` contains one structured JSON contract with name, semantic version,
description, intents, inputs, Tool whitelist, workflow, minimum Evidence, stop conditions, fallback,
output contract, safety constraints, budget and enabled state. `SkillLoader` reads these contracts;
`SkillRegistry` rejects invalid versions, duplicate Intent mappings, missing Tools, non-whitelisted
steps, write Tools and invalid budgets.

Dry Run returns selected Skill/version, planned steps, allowed Tools, Evidence requirements, stop
conditions, fallbacks and budget without executing any Tool.

## Intent and Skill catalog

| Intent | Skill/version | Max calls | Primary fallback |
| --- | --- | ---: | --- |
| `TREND_DISCOVERY` | `trend-research-v1.0.0` | 8 | `CATEGORY_AGGREGATE_ONLY` / insufficient history |
| `FUTURE_PREDICTION` | `future-prediction-v1.0.0` | 4 | `CURRENT_SIGNAL_ANALYSIS` |
| `LEARNING_RECOMMENDATION` | `learning-recommendation-v1.0.0` | 15 | `STRUCTURED_ONLY_RESULT` |
| `ENTERPRISE_SELECTION` | `enterprise-selection-v1.0.0` | 15 | `INSUFFICIENT_EVIDENCE` |
| `PROJECT_ANALYSIS` | `project-analysis-v1.0.0` | 12 | partial result |
| `PROJECT_COMPARISON` | `project-comparison-v1.0.0` | 15 | structured-only/low-confidence result |

## Evidence, confidence and NULL

Trend requires algorithm version, Evidence and completeness. Learning and Enterprise respect their
existing confidence ranking gates. Enterprise recommendation additionally requires Maintenance
Evidence; Knowledge `NOT_INGESTED` means Evidence has not been collected, not that Security or
Architecture documents do not exist. Low-confidence raw values may be returned only with
`LOW_CONFIDENCE`/`DATA_ACCUMULATING`, never as a strong recommendation.

Skills preserve `null`, `VALUE`, `MISSING`, `INSUFFICIENT_HISTORY`, `NOT_INGESTED` and
`DOCUMENT_NOT_FOUND`. Missing facts are never replaced by LLM judgment or zero.

## Deterministic executor

`SkillExecutor` is a thin test/runtime harness that follows declared steps. It cannot choose new
Tools, re-plan, loop autonomously or write a natural-language answer. It stops at minimum Evidence,
required Tool failure or the Tool budget. Its trace contains Skill/version, executed Tools, summed
duration, status, warnings, Evidence count, stop reason and budget usage, without secrets.

Forecast always starts with `get_project_forecast`. Current production state is `NOT_READY`, so the
workflow falls back to Trend + Potential and labels the result `CURRENT_SIGNAL_ANALYSIS`; it never
runs a VALIDATED model or produces a probability.
