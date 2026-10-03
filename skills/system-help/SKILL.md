# System Help

```json
{
  "name": "system-help",
  "version": "system-help-v1.0.0",
  "description": "Explain AgentRadar metrics, data collection, model lifecycle, and product usage from trusted built-in documentation.",
  "supported_intents": ["SYSTEM_HELP"],
  "required_inputs": ["help_topic"],
  "optional_inputs": [],
  "allowed_tools": ["get_system_help"],
  "workflow_steps": [
    {"id": "help", "tool": "get_system_help", "mode": "constraints", "constraint_keys": ["help_topic"], "argument_map": {"help_topic": "topic"}}
  ],
  "evidence_requirements": ["trusted built-in AgentRadar documentation", "topic", "explanation", "limitations"],
  "stop_conditions": ["help content returned", "tool budget exhausted"],
  "fallback_policy": {"UNKNOWN_TOPIC": "GENERAL_HELP", "TOOL_FAILURE": "PARTIAL_RESULT"},
  "output_contract": {"type": "system_help", "repository_facts_forbidden": true},
  "safety_constraints": ["NO_REPOSITORY_FACTS", "NO_SCORE_RECALCULATION", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 1,
  "enabled": true
}
```
