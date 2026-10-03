# Watchlist Query

```json
{
  "name": "watchlist-query",
  "version": "watchlist-query-v1.0.0",
  "description": "Read the current user's persisted Watchlist without modifying it.",
  "supported_intents": ["WATCHLIST_QUERY"],
  "required_inputs": [],
  "optional_inputs": [],
  "allowed_tools": ["get_watchlist"],
  "workflow_steps": [{"id": "watchlist", "tool": "get_watchlist", "mode": "single"}],
  "evidence_requirements": ["persisted Watchlist items"],
  "stop_conditions": ["Watchlist returned", "tool budget exhausted"],
  "fallback_policy": {"TOOL_FAILURE": "PARTIAL_RESULT"},
  "output_contract": {"type": "watchlist_evidence", "natural_language_answer": false},
  "safety_constraints": ["READ_ONLY_TOOLS_ONLY", "NO_AUTONOMOUS_WATCHLIST_WRITE"],
  "tool_call_budget": 1,
  "enabled": true
}
```
