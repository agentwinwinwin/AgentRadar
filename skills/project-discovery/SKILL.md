# Project Discovery

```json
{
  "name": "project-discovery",
  "version": "project-discovery-v1.0.0",
  "description": "Search persisted AI Agent repositories without forcing a trend or recommendation interpretation.",
  "supported_intents": ["PROJECT_DISCOVERY"],
  "required_inputs": [],
  "optional_inputs": ["category", "query", "min_stars", "max_stars", "limit", "sort"],
  "allowed_tools": ["search_projects"],
  "workflow_steps": [
    {"id": "search", "tool": "search_projects", "mode": "search", "arguments": {"sort": "-stars", "limit": 10}, "constraint_keys": ["category", "query", "min_stars", "max_stars", "limit", "sort"], "stop_on_error": true}
  ],
  "evidence_requirements": ["persisted repository metadata", "category", "stars", "data timestamp when available"],
  "stop_conditions": ["requested bounded repository list returned", "tool budget exhausted"],
  "fallback_policy": {"NO_RESULTS": "EMPTY_RESULT", "TOOL_FAILURE": "PARTIAL_RESULT"},
  "output_contract": {"type": "repository_discovery", "ranking_claim_requires_explicit_sort": true},
  "safety_constraints": ["PERSISTED_DATA_ONLY", "NO_GITHUB_LIVE_REQUEST", "NULL_IS_NOT_ZERO", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 1,
  "enabled": true
}
```
