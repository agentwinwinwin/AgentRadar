# Future Prediction

```json
{
  "name": "future-prediction",
  "version": "future-prediction-v1.1.0",
  "description": "Read production Forecast status and fall back to current deterministic signals.",
  "supported_intents": ["FUTURE_PREDICTION"],
  "required_inputs": ["repository_id"],
  "optional_inputs": [],
  "allowed_tools": ["search_projects", "get_project_forecast", "get_project_trend", "get_project_potential", "get_project"],
  "workflow_steps": [
    {"id": "forecast", "tool": "get_project_forecast", "mode": "entity", "stop_on_error": true},
    {"id": "project", "tool": "get_project", "mode": "entity", "when": "FORECAST_NOT_READY"},
    {"id": "trend", "tool": "get_project_trend", "mode": "entity", "when": "FORECAST_NOT_READY"},
    {"id": "potential", "tool": "get_project_potential", "mode": "entity", "when": "FORECAST_NOT_READY"}
  ],
  "evidence_requirements": ["forecast_status", "active_model_status", "trend_completeness", "potential_confidence"],
  "stop_conditions": ["READY Forecast evidence collected", "NOT_READY fallback current signals collected", "required Forecast Tool failed"],
  "fallback_policy": {"FORECAST_NOT_READY": "CURRENT_SIGNAL_ANALYSIS", "LOW_POTENTIAL_CONFIDENCE": "TREND_ONLY"},
  "output_contract": {"type": "forecast_status_or_current_signals", "production_probability_requires_active_model": true},
  "safety_constraints": ["NEVER_RUN_VALIDATED_MODEL", "NEVER_INVENT_PROBABILITY", "CURRENT_SIGNALS_ARE_NOT_FORECAST", "READ_ONLY_TOOLS_ONLY"],
  "tool_call_budget": 5,
  "enabled": true
}
```
