from apps.repositories.classifiers import classify_repository
from apps.repositories.models import RepositoryCategory


def test_topics_have_priority_in_rule_classifier() -> None:
    category = classify_repository(
        topics=["coding-agent"],
        description="A general AI agent framework",
    )

    assert category == RepositoryCategory.CODING_AGENT


def test_unknown_repository_uses_other_agent() -> None:
    assert (
        classify_repository(topics=["python"], description="An experimental project")
        == RepositoryCategory.OTHER_AGENT
    )
