# Enterprise Selection

```json
{
  "name": "enterprise-selection",
  "version": "enterprise-selection-v1.1.0",
  "description": "Compare enterprise candidates using score confidence and adoption evidence.",
  "supported_intents": ["ENTERPRISE_SELECTION"],
  "required_inputs": [],
  "optional_inputs": ["category", "query", "min_stars", "max_stars", "limit"],
  "allowed_tools": ["search_projects", "get_enterprise_score", "get_project_trend", "get_project_potential", "get_project_knowledge_summary", "search_repository_knowledge", "compare_projects"],
  "workflow_steps": [
    {"id": "search", "tool": "search_projects", "mode": "search", "arguments": {"sort": "-enterprise", "limit": 10}, "constraint_keys": ["category", "query", "min_stars", "max_stars", "limit"], "stop_on_error": true},
    {"id": "enterprise", "tool": "get_enterprise_score", "mode": "each_candidate", "limit": 3},
    {"id": "trend", "tool": "get_project_trend", "mode": "each_candidate", "limit": 3},
    {"id": "knowledge_summary", "tool": "get_project_knowledge_summary", "mode": "each_candidate", "limit": 3},
    {"id": "knowledge", "tool": "search_repository_knowledge", "mode": "each_candidate", "limit": 2, "arguments": {"query": "security license architecture deployment release", "top_k": 3}, "when": "KNOWLEDGE_INGESTED"},
    {"id": "compare", "tool": "compare_projects", "mode": "compare_candidates", "limit": 2}
  ],
  "evidence_requirements": ["enterprise_score", "enterprise_confidence", "maintenance VALUE", "license", "knowledge_status", "security/architecture/deployment evidence when ingested"],
  "stop_conditions": ["at least two candidates have minimum enterprise evidence and comparison", "tool budget exhausted"],
  "fallback_policy": {"KNOWLEDGE_NOT_INGESTED": "STRUCTURED_ONLY_RESULT", "LOW_ENTERPRISE_CONFIDENCE": "INSUFFICIENT_EVIDENCE", "LOW_POTENTIAL_CONFIDENCE": "TREND_ONLY"},
  "output_contract": {"type": "enterprise_candidates", "absolute_best_claim_forbidden": true},
  "safety_constraints": ["NOT_INGESTED_DOES_NOT_MEAN_NO_SECURITY_DOC", "STARS_ARE_NOT_CORE_EVIDENCE", "POTENTIAL_IS_AUXILIARY", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 15,
  "enabled": true
}
```
