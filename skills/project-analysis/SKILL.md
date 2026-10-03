# Project Analysis

```json
{
  "name": "project-analysis",
  "version": "project-analysis-v1.1.0",
  "description": "Collect a complete structured evidence package for one Repository.",
  "supported_intents": ["PROJECT_ANALYSIS"],
  "required_inputs": ["repository_id"],
  "optional_inputs": [],
  "allowed_tools": ["search_projects", "get_project", "get_project_trend", "get_project_potential", "get_project_forecast", "get_learning_score", "get_enterprise_score", "get_project_knowledge_summary", "search_repository_knowledge"],
  "workflow_steps": [
    {"id": "project", "tool": "get_project", "mode": "entity"},
    {"id": "trend", "tool": "get_project_trend", "mode": "entity"},
    {"id": "potential", "tool": "get_project_potential", "mode": "entity"},
    {"id": "forecast", "tool": "get_project_forecast", "mode": "entity"},
    {"id": "learning", "tool": "get_learning_score", "mode": "entity"},
    {"id": "enterprise", "tool": "get_enterprise_score", "mode": "entity"},
    {"id": "knowledge_summary", "tool": "get_project_knowledge_summary", "mode": "entity"},
    {"id": "knowledge", "tool": "search_repository_knowledge", "mode": "entity", "arguments": {"query": "purpose architecture installation security risks release", "top_k": 5}, "when": "KNOWLEDGE_INGESTED"}
  ],
  "evidence_requirements": ["repository metadata", "Trend", "Potential", "Forecast status", "Learning", "Enterprise", "Knowledge status"],
  "stop_conditions": ["all available structured dimensions and bounded Knowledge evidence collected", "tool budget exhausted"],
  "fallback_policy": {"INDIVIDUAL_TOOL_FAILURE": "PARTIAL_RESULT", "KNOWLEDGE_NOT_INGESTED": "STRUCTURED_ONLY_RESULT", "FORECAST_NOT_READY": "CURRENT_SIGNAL_ANALYSIS"},
  "output_contract": {"type": "partial_tolerant_project_evidence", "natural_language_answer": false},
  "safety_constraints": ["ONE_TOOL_FAILURE_MUST_NOT_ABORT", "NULL_IS_NOT_ZERO", "NO_LLM_SCORING", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 12,
  "enabled": true
}
```
