# Project Comparison

```json
{
  "name": "project-comparison",
  "version": "project-comparison-v1.1.0",
  "description": "Collect goal-conditioned comparison evidence for two to five repositories.",
  "supported_intents": ["PROJECT_COMPARISON"],
  "required_inputs": ["repositories"],
  "optional_inputs": ["comparison_goal"],
  "allowed_tools": ["search_projects", "compare_projects", "get_learning_score", "get_enterprise_score", "get_project_trend", "get_project_potential", "search_repository_knowledge"],
  "workflow_steps": [
    {"id": "compare", "tool": "compare_projects", "mode": "compare_entities", "stop_on_error": true},
    {"id": "trend", "tool": "get_project_trend", "mode": "each_entity"},
    {"id": "potential", "tool": "get_project_potential", "mode": "each_entity"},
    {"id": "learning", "tool": "get_learning_score", "mode": "each_entity"},
    {"id": "enterprise", "tool": "get_enterprise_score", "mode": "each_entity"},
    {"id": "knowledge", "tool": "search_repository_knowledge", "mode": "each_entity", "arguments": {"query": "architecture installation security deployment", "top_k": 2}}
  ],
  "evidence_requirements": ["comparison goal", "Category", "Activity", "Trend", "Potential", "Learning", "Enterprise", "Forecast status", "Knowledge evidence"],
  "stop_conditions": ["goal-relevant evidence collected for every project", "tool budget exhausted"],
  "fallback_policy": {"KNOWLEDGE_NOT_INGESTED": "STRUCTURED_ONLY_RESULT", "LOW_CONFIDENCE": "MARK_LOW_CONFIDENCE", "INDIVIDUAL_TOOL_FAILURE": "PARTIAL_RESULT"},
  "output_contract": {"type": "goal_conditioned_comparison", "absolute_winner_claim_forbidden": true},
  "safety_constraints": ["NO_ABSOLUTE_BEST_WITHOUT_USER_GOAL", "NULL_IS_NOT_ZERO", "PRESERVE_CONFIDENCE", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 15,
  "enabled": true
}
```
