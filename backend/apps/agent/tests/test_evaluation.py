import json
from collections import Counter
from pathlib import Path

from apps.skills.contracts import Intent


def test_fixed_evaluation_set_has_balanced_thirty_questions():
    path = Path(__file__).parent / "fixtures" / "evaluation.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    counts = Counter(case["intent"] for case in cases)
    assert len(cases) == 30
    original_intents = {
        Intent.TREND_DISCOVERY,
        Intent.FUTURE_PREDICTION,
        Intent.LEARNING_RECOMMENDATION,
        Intent.ENTERPRISE_SELECTION,
        Intent.PROJECT_ANALYSIS,
        Intent.PROJECT_COMPARISON,
    }
    assert counts == {intent.value: 5 for intent in original_intents}
    assert all(case["query"].strip() for case in cases)
