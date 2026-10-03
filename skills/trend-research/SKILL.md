# Trend Research

```json
{
  "name": "trend-research",
  "version": "trend-research-v1.1.0",
  "description": "Find currently notable projects using confidence-gated Trend evidence.",
  "supported_intents": ["TREND_DISCOVERY"],
  "required_inputs": [],
  "optional_inputs": ["category", "query", "min_stars", "max_stars", "limit"],
  "allowed_tools": ["search_projects", "get_category_trend"],
  "workflow_steps": [
    {"id": "search", "tool": "search_projects", "mode": "search", "arguments": {"sort": "-trend", "limit": 10}, "constraint_keys": ["category", "query", "min_stars", "max_stars", "limit"], "stop_on_error": true},
    {"id": "category", "tool": "get_category_trend", "mode": "category", "when": "CATEGORY_PROVIDED"}
  ],
  "evidence_requirements": ["trend_score", "algorithm_version", "data_completeness", "trend_evidence"],
  "stop_conditions": ["requested persisted ranking returned", "tool budget exhausted"],
  "fallback_policy": {"INSUFFICIENT_TREND_HISTORY": "INSUFFICIENT_EVIDENCE", "NO_CATEGORY_MODEL": "CATEGORY_AGGREGATE_ONLY", "LOW_POTENTIAL_CONFIDENCE": "TREND_ONLY"},
  "output_contract": {"type": "structured_ranking", "long_term_claims_forbidden": true},
  "safety_constraints": ["NULL_IS_NOT_ZERO", "SHORT_HISTORY_IS_NOT_LONG_TERM_TREND", "NO_LLM_SCORING", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 2,
  "enabled": true
}
```
