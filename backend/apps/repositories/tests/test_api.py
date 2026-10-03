from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.activities.models import RepositoryActivityMetric, RepositoryRelease
from apps.enterprise.engine import ALGORITHM_VERSION as ENTERPRISE_VERSION
from apps.enterprise.models import RepositoryEnterpriseScore
from apps.forecasts.models import MLModel, ModelStatus, RepositoryForecast
from apps.github.fakes import FakeGitHubClient
from apps.learning.engine import ALGORITHM_VERSION as LEARNING_VERSION
from apps.learning.models import RepositoryLearningScore
from apps.potentials.engine import ALGORITHM_VERSION as POTENTIAL_ALGORITHM_VERSION
from apps.potentials.models import RepositoryPotentialScore
from apps.repositories.models import RepositoryCategory
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload
from apps.snapshots.models import RepositorySnapshot
from apps.trends.engine import ALGORITHM_VERSION
from apps.trends.models import HypeRiskStatus, LifecycleStage, RepositoryTrendScore


def create_project(index: int, *, with_trend: bool = True, null_stars: bool = False):
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(
            id=50_000 + index,
            full_name=f"api/project-{index}",
            name=f"project-{index}",
            stargazers_count=None if null_stars else index * 100,
            forks_count=index * 10,
        )
    )
    repository.category = RepositoryCategory.BROWSER_AGENT
    repository.save(update_fields=("category", "updated_at"))
    if with_trend:
        RepositoryTrendScore.objects.create(
            repository=repository,
            trend_score=index * 10,
            momentum_score=index * 9,
            development_score=index * 8,
            community_score=index * 7,
            delivery_score=index * 6,
            adoption_score=index * 5,
            topic_momentum_score=None,
            maintenance_score=index * 4,
            hype_risk=None,
            hype_risk_status=HypeRiskStatus.INSUFFICIENT_HISTORY,
            lifecycle_stage=(LifecycleStage.BREAKOUT if index >= 8 else LifecycleStage.EMERGING),
            data_completeness=0.75,
            algorithm_version=ALGORITHM_VERSION,
            calculated_at=timezone.now(),
            evidence={"missing_inputs": ["topic_momentum"]},
        )
    return repository


def create_potential(repository, *, score: float, confidence: float = 0.6):
    return RepositoryPotentialScore.objects.create(
        repository=repository,
        potential_score=score,
        confidence=confidence,
        algorithm_version=POTENTIAL_ALGORITHM_VERSION,
        calculated_at=timezone.now(),
        evidence={
            "candidate_flags": {
                "high_potential": score >= 75 and confidence >= 0.55,
                "potential_candidate": score >= 65 and confidence >= 0.45,
                "breakout_candidate": False,
            },
            "missing_inputs": ["topic_momentum", "novelty", "hype_risk"],
        },
    )


@pytest.mark.django_db
def test_dashboard_uses_persisted_trend_and_potential_scores() -> None:
    runner_up = create_project(7)
    high = create_project(9)
    create_potential(runner_up, score=80, confidence=0.56)
    create_potential(high, score=85)

    response = APIClient().get("/api/v1/dashboard")

    assert response.status_code == 200
    assert response.data["statistics"]["tracked_projects"] == 2
    assert response.data["statistics"]["breakout_projects"] == 1
    assert response.data["top_trend_projects"][0]["trend_score"] == 90.0
    assert response.data["statistics"]["high_potential_projects"] == 2
    assert response.data["high_potential_projects"][0]["potential_score"] == 85.0
    assert response.data["high_potential_projects"][1]["potential_score"] == 80.0
    assert response.data["high_potential_projects"][0]["potential_confidence"] == 0.6
    assert response.data["category_trend"]["status"] == "ACCUMULATING"
    assert response.data["category_trend"]["fallback"] == "CATEGORY_DISTRIBUTION"


@pytest.mark.django_db
def test_dashboard_ranking_excludes_null_and_insufficient_completeness() -> None:
    missing = create_project(1, with_trend=False)
    insufficient = create_project(10)
    eligible = create_project(8)
    RepositoryTrendScore.objects.filter(repository=insufficient).update(data_completeness=0.1)

    response = APIClient().get("/api/v1/dashboard")

    assert response.status_code == 200
    ranked_ids = [item["id"] for item in response.data["top_trend_projects"]]
    assert ranked_ids == [eligible.id]
    assert missing.id not in ranked_ids
    assert insufficient.id not in ranked_ids


@pytest.mark.django_db
def test_discover_score_ranking_excludes_missing_data() -> None:
    missing = create_project(1, with_trend=False)
    scored = create_project(2)

    response = APIClient().get("/api/v1/projects", {"sort": "-trend"})

    assert response.status_code == 200
    assert [item["id"] for item in response.data["results"]] == [scored.id]
    assert missing.id not in [item["id"] for item in response.data["results"]]


@pytest.mark.django_db
def test_discover_ranking_places_insufficient_data_after_eligible_projects() -> None:
    insufficient_trend = create_project(10)
    eligible_trend = create_project(8)
    RepositoryTrendScore.objects.filter(repository=insufficient_trend).update(
        data_completeness=0.02
    )

    trend_response = APIClient().get("/api/v1/projects", {"sort": "-trend"})

    assert trend_response.status_code == 200
    assert [item["id"] for item in trend_response.data["results"]] == [eligible_trend.id]
    assert insufficient_trend.id not in [item["id"] for item in trend_response.data["results"]]

    insufficient_potential = create_project(7)
    eligible_potential = create_project(6)
    create_potential(insufficient_potential, score=99, confidence=0.02)
    create_potential(eligible_potential, score=70, confidence=0.45)

    potential_response = APIClient().get("/api/v1/projects", {"sort": "-potential"})

    assert potential_response.status_code == 200
    potential_ids = [item["id"] for item in potential_response.data["results"]]
    assert eligible_potential.id in potential_ids
    assert insufficient_potential.id not in potential_ids


@pytest.mark.django_db
def test_discover_filters_sorts_paginates_and_preserves_null() -> None:
    create_project(2, null_stars=True)
    create_project(8)

    response = APIClient().get(
        "/api/v1/projects",
        {"category": RepositoryCategory.BROWSER_AGENT, "trend_min": 10, "page_size": 1},
    )

    assert response.status_code == 200
    assert response.data["count"] == 2
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["trend_score"] == 80.0

    null_response = APIClient().get("/api/v1/projects", {"q": "project-2"})
    assert null_response.data["results"][0]["stars"] is None


@pytest.mark.django_db
def test_discover_rejects_invalid_parameters() -> None:
    response = APIClient().get("/api/v1/projects", {"min_stars": 10, "max_stars": 1})
    assert response.status_code == 400

    response = APIClient().get("/api/v1/projects", {"trend_min": 101})
    assert response.status_code == 400

    response = APIClient().get("/api/v1/projects", {"potential_min": 101})
    assert response.status_code == 400

    response = APIClient().get("/api/v1/projects", {"learning_min": 101})
    assert response.status_code == 400
    response = APIClient().get("/api/v1/projects", {"enterprise_min": 101})
    assert response.status_code == 400


@pytest.mark.django_db
def test_project_detail_metrics_and_trend_are_database_backed() -> None:
    repository = create_project(8)
    create_potential(repository, score=82)
    observed_at = timezone.now()
    RepositorySnapshot.objects.create(
        repository=repository,
        snapshot_at=observed_at,
        snapshot_date=observed_at.date(),
        snapshot_bucket=observed_at.strftime("%Y-%m-%dT%H"),
        stars=None,
        forks=5,
        data_completeness=0.5,
    )
    RepositoryActivityMetric.objects.create(
        repository=repository,
        metric_date=observed_at.date(),
        commits_7d=None,
        commits_30d=12,
    )
    RepositoryRelease.objects.create(
        repository=repository,
        github_release_id=90_000,
        tag_name="v1",
        published_at=observed_at,
        content_hash="0" * 64,
    )

    client = APIClient()
    detail = client.get(f"/api/v1/projects/{repository.id}")
    metrics = client.get(f"/api/v1/projects/{repository.id}/metrics", {"range": "7d"})
    trend = client.get(f"/api/v1/projects/{repository.id}/trend")
    potential = client.get(f"/api/v1/projects/{repository.id}/potential")

    assert detail.status_code == 200
    assert detail.data["github_url"] == f"https://github.com/{repository.full_name}"
    assert detail.data["latest_snapshot"]["stars"] is None
    assert detail.data["latest_activity"]["commits_7d"] is None
    assert metrics.status_code == 200
    assert metrics.data["range"] == "7d"
    assert metrics.data["snapshots"][0]["stars"] is None
    assert metrics.data["releases"][0]["tag_name"] == "v1"
    assert trend.status_code == 200
    assert trend.data["trend_score"] == 80.0
    assert trend.data["hype_risk"] is None
    assert trend.data["hype_risk_status"] == HypeRiskStatus.INSUFFICIENT_HISTORY
    assert trend.data["evidence"] == {"missing_inputs": ["topic_momentum"]}
    assert potential.status_code == 200
    assert potential.data["potential_score"] == 82.0
    assert potential.data["confidence"] == 0.6
    assert potential.data["high_potential"] is True
    assert "forecast_probability" not in potential.data


@pytest.mark.django_db
def test_metrics_validates_range_and_all_endpoints_return_404() -> None:
    repository = create_project(1)
    response = APIClient().get(f"/api/v1/projects/{repository.id}/metrics", {"range": "365d"})
    assert response.status_code == 400

    for path in (
        "/api/v1/projects/999999",
        "/api/v1/projects/999999/metrics",
        "/api/v1/projects/999999/trend",
        "/api/v1/projects/999999/potential",
    ):
        assert APIClient().get(path).status_code == 404


@pytest.mark.django_db
def test_metrics_excludes_rows_outside_selected_range() -> None:
    repository = create_project(3)
    old_at = datetime.now(UTC) - timedelta(days=31)
    RepositorySnapshot.objects.create(
        repository=repository,
        snapshot_at=old_at,
        snapshot_date=old_at.date(),
        snapshot_bucket=old_at.strftime("%Y-%m-%dT%H"),
        stars=1,
        data_completeness=0.2,
    )

    response = APIClient().get(f"/api/v1/projects/{repository.id}/metrics", {"range": "30d"})
    assert response.status_code == 200
    assert response.data["snapshots"] == []


@pytest.mark.django_db
def test_trend_endpoint_reports_not_available_without_fabricated_zero() -> None:
    repository = create_project(4, with_trend=False)
    response = APIClient().get(f"/api/v1/projects/{repository.id}/trend")

    assert response.status_code == 200
    assert response.data["status"] == "NOT_AVAILABLE"
    assert response.data["hype_risk"] is None
    assert response.data["hype_risk_status"] == HypeRiskStatus.INSUFFICIENT_HISTORY


@pytest.mark.django_db
def test_potential_discover_filter_sort_and_not_available_null() -> None:
    low = create_project(5)
    high = create_project(9)
    create_potential(low, score=60)
    create_potential(high, score=85)

    response = APIClient().get("/api/v1/projects", {"potential_min": 70, "sort": "-potential"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["id"] == high.id

    without = create_project(3)
    response = APIClient().get(f"/api/v1/projects/{without.id}/potential")
    assert response.status_code == 200
    assert response.data["status"] == "NOT_AVAILABLE"
    assert response.data["potential_score"] is None


@pytest.mark.django_db
def test_forecast_api_is_not_ready_without_active_model() -> None:
    repository = create_project(99, with_trend=False)

    response = APIClient().get(f"/api/v1/projects/{repository.id}/forecast")

    assert response.status_code == 200
    assert response.data["status"] == "NOT_READY"
    assert response.data["forecast"] is None
    assert response.data["fallback"] == "POTENTIAL_SCORE"
    assert response.data["definition"] == ("未来30天进入同 Category 高开发活跃增长组的概率")


@pytest.mark.django_db
def test_forecast_api_exposes_active_binary_model_probability_and_safe_inputs() -> None:
    repository = create_project(100, with_trend=False)
    now = timezone.now()
    model = MLModel.objects.create(
        model_name="activity-growth-30d",
        model_version="forecast-v1-active-test",
        feature_version="feature-v1.0.0",
        label_version="label-v1.2.0",
        algorithm="random_forest",
        training_start=now - timedelta(days=180),
        training_end=now - timedelta(days=30),
        validation_metrics={},
        test_metrics={},
        dataset_quality={"passed": True},
        feature_importance={},
        artifact_path="/not-used",
        artifact_sha256="a" * 64,
        status=ModelStatus.ACTIVE,
    )
    RepositoryForecast.objects.create(
        repository=repository,
        model=model,
        model_version=model.model_version,
        sample_at=now,
        high_growth_probability=0.73,
        prediction=1,
        confidence=0.46,
        feature_snapshot={
            "features": {
                "current_stars": 1200,
                "commit_30d": 42,
                "repository_id": repository.id,
            }
        },
    )

    response = APIClient().get(f"/api/v1/projects/{repository.id}/forecast")

    assert response.status_code == 200
    assert response.data["forecast"]["forecast_type"] == "ACTIVITY_FORECAST_V1"
    assert response.data["forecast"]["prediction"] == 1
    assert response.data["forecast"]["high_growth_probability"] == 0.73
    assert response.data["forecast"]["input_features"] == {
        "current_stars": 1200,
        "commit_30d": 42,
    }
    assert "repository_id" not in response.data["forecast"]["input_features"]


@pytest.mark.django_db
def test_active_star_v2_percentile_becomes_displayed_high_potential_score() -> None:
    repository = create_project(9)
    create_potential(repository, score=60, confidence=0.7)
    now = timezone.now()
    model = MLModel.objects.create(
        model_name="star-growth-30d",
        model_version="forecast-v2-test",
        feature_version="feature-v2.0.0",
        label_version="label-v2.0.0",
        algorithm="xgboost",
        training_start=now - timedelta(days=180),
        training_end=now - timedelta(days=30),
        validation_metrics={},
        test_metrics={},
        dataset_quality={"passed": True},
        feature_importance={},
        artifact_path="/not-used",
        artifact_sha256="a" * 64,
        status=ModelStatus.ACTIVE,
    )
    RepositoryForecast.objects.create(
        repository=repository,
        model=model,
        model_version=model.model_version,
        sample_at=now - timedelta(days=90),
        high_growth_probability=0.82,
        prediction=1,
        confidence=0.8,
        predicted_activity_percentile=92.5,
        percentile_model_version="percentile-v2-test",
        feature_snapshot={
            "features": {
                "star_growth_7d": 12.5,
                "star_growth_30d": 38.0,
                "fork_growth_30d": 9.0,
                "commit_30d": 42,
                "repository_id": repository.id,
            }
        },
    )

    response = APIClient().get("/api/v1/dashboard")

    project = next(
        item
        for item in response.data["high_potential_projects"]
        if item["id"] == repository.id
    )
    assert project["potential_score"] == 92.5
    assert project["deterministic_potential_score"] == 60.0
    assert project["potential_score_source"] == "STAR_FORECAST_V2"
    assert response.data["high_potential_ranking"]["source"] == "STAR_FORECAST_V2"

    forecast_response = APIClient().get(f"/api/v1/projects/{repository.id}/forecast")
    assert forecast_response.data["status"] == "NOT_READY"
    assert forecast_response.data["forecast"] is None


@pytest.mark.django_db
def test_learning_enterprise_api_and_ranking_require_confidence() -> None:
    eligible = create_project(71)
    insufficient = create_project(72)
    now = timezone.now()
    for repository, confidence, score in (
        (eligible, 0.7, 75),
        (insufficient, 0.2, 99),
    ):
        RepositoryLearningScore.objects.create(
            repository=repository,
            score=score,
            confidence=confidence,
            algorithm_version=LEARNING_VERSION,
            evidence={"knowledge_status": "NOT_INGESTED"},
            calculated_at=now,
        )
        RepositoryEnterpriseScore.objects.create(
            repository=repository,
            score=score,
            confidence=confidence,
            recommendation="POC",
            algorithm_version=ENTERPRISE_VERSION,
            evidence={"knowledge_status": "NOT_INGESTED"},
            calculated_at=now,
        )

    learning = APIClient().get(f"/api/v1/projects/{eligible.id}/learning")
    enterprise = APIClient().get(f"/api/v1/projects/{eligible.id}/enterprise")
    ranking = APIClient().get("/api/v1/projects", {"sort": "-learning"})

    assert learning.status_code == enterprise.status_code == 200
    assert learning.data["ranking_eligible"] is True
    assert enterprise.data["recommendation"] == "POC"
    assert [item["id"] for item in ranking.data["results"]] == [eligible.id]
