# Learning Recommendation

```json
{
  "name": "learning-recommendation",
  "version": "learning-recommendation-v1.1.0",
  "description": "Select learning candidates using Learning confidence, maintenance and Knowledge evidence.",
  "supported_intents": ["LEARNING_RECOMMENDATION"],
  "required_inputs": [],
  "optional_inputs": ["category", "query", "min_stars", "max_stars", "limit"],
  "allowed_tools": ["search_projects", "get_learning_score", "get_project_trend", "get_project_knowledge_summary", "search_repository_knowledge", "compare_projects"],
  "workflow_steps": [
    {"id": "search", "tool": "search_projects", "mode": "search", "arguments": {"sort": "-learning", "limit": 10}, "constraint_keys": ["category", "query", "min_stars", "max_stars", "limit"], "stop_on_error": true},
    {"id": "learning", "tool": "get_learning_score", "mode": "each_candidate", "limit": 3},
    {"id": "trend", "tool": "get_project_trend", "mode": "each_candidate", "limit": 3},
    {"id": "knowledge_summary", "tool": "get_project_knowledge_summary", "mode": "each_candidate", "limit": 3},
    {"id": "knowledge", "tool": "search_repository_knowledge", "mode": "each_candidate", "limit": 3, "arguments": {"query": "architecture installation getting started examples testing", "top_k": 3}, "when": "KNOWLEDGE_INGESTED"},
    {"id": "compare", "tool": "compare_projects", "mode": "compare_candidates", "limit": 3}
  ],
  "evidence_requirements": ["learning_score", "learning_confidence", "maintenance_status", "knowledge_status", "README/docs/architecture evidence"],
  "stop_conditions": ["three confidence-eligible candidates have Learning, Trend and Knowledge evidence", "tool budget exhausted"],
  "fallback_policy": {"KNOWLEDGE_NOT_INGESTED": "STRUCTURED_ONLY_RESULT", "LOW_LEARNING_CONFIDENCE": "INSUFFICIENT_EVIDENCE", "TREND_UNAVAILABLE": "MAINTENANCE_UNKNOWN"},
  "output_contract": {"type": "goal_conditioned_learning_candidates", "stars_are_not_primary": true},
  "safety_constraints": ["NULL_IS_NOT_ZERO", "NOT_INGESTED_IS_NOT_DOCUMENT_NOT_FOUND", "NO_STAR_ONLY_RECOMMENDATION", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 15,
  "enabled": true
}
```
