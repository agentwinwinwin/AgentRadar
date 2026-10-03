# Potential Research

```json
{
  "name": "potential-research",
  "version": "potential-research-v1.0.0",
  "description": "Query the persisted explainable Potential ranking without treating it as a forecast probability.",
  "supported_intents": ["POTENTIAL_DISCOVERY"],
  "required_inputs": [],
  "optional_inputs": ["category", "query", "min_stars", "max_stars", "limit"],
  "allowed_tools": ["search_projects"],
  "workflow_steps": [
    {"id": "search", "tool": "search_projects", "mode": "search", "arguments": {"sort": "-potential", "limit": 10}, "constraint_keys": ["category", "query", "min_stars", "max_stars", "limit"], "stop_on_error": true}
  ],
  "evidence_requirements": ["potential_score", "potential_confidence", "potential_status", "data_completeness"],
  "stop_conditions": ["ranked candidates returned", "tool budget exhausted"],
  "fallback_policy": {"NO_CANDIDATES": "NO_MATCH", "LOW_POTENTIAL_CONFIDENCE": "INSUFFICIENT_EVIDENCE"},
  "output_contract": {"type": "potential_ranking", "forecast_probability_forbidden": true},
  "safety_constraints": ["NULL_IS_NOT_ZERO", "POTENTIAL_IS_NOT_FORECAST", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 1,
  "enabled": true
}
```
