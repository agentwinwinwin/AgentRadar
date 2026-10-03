# Scheduled Report Query

```json
{
  "name": "report-query",
  "version": "report-query-v1.0.0",
  "description": "Read the latest deterministic Daily or Weekly structured report.",
  "supported_intents": ["REPORT_QUERY"],
  "required_inputs": ["report_type"],
  "optional_inputs": [],
  "allowed_tools": ["get_latest_report"],
  "workflow_steps": [{"id": "report", "tool": "get_latest_report", "mode": "constraints", "constraint_keys": ["report_type"]}],
  "evidence_requirements": ["structured facts and existing Alert evidence"],
  "stop_conditions": ["Report returned", "tool budget exhausted"],
  "fallback_policy": {"REPORT_NOT_FOUND": "EMPTY_RESULT", "TOOL_FAILURE": "PARTIAL_RESULT"},
  "output_contract": {"type": "scheduled_report_evidence", "natural_language_answer": false},
  "safety_constraints": ["READ_ONLY_TOOLS_ONLY", "NO_LLM_SCORING", "NO_LLM_FACT_CREATION"],
  "tool_call_budget": 1,
  "enabled": true
}
```
