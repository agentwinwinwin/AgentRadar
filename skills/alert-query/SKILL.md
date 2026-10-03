# Alert Query

```json
{
  "name": "alert-query",
  "version": "alert-query-v1.0.0",
  "description": "Read recent deterministic Alerts and their evidence for one Repository.",
  "supported_intents": ["ALERT_QUERY"],
  "required_inputs": ["repository_id"],
  "optional_inputs": [],
  "allowed_tools": ["search_projects", "get_project_alerts"],
  "workflow_steps": [{"id": "alerts", "tool": "get_project_alerts", "mode": "entity", "arguments": {"limit": 20}}],
  "evidence_requirements": ["rule version", "detected time", "structured Alert evidence"],
  "stop_conditions": ["Alerts returned", "tool budget exhausted"],
  "fallback_policy": {"NO_ALERT": "EMPTY_RESULT", "TOOL_FAILURE": "PARTIAL_RESULT"},
  "output_contract": {"type": "alert_evidence", "natural_language_answer": false},
  "safety_constraints": ["READ_ONLY_TOOLS_ONLY", "NO_LLM_ALERT_DECISION", "NULL_IS_NOT_ZERO"],
  "tool_call_budget": 2,
  "enabled": true
}
```
