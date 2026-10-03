from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.repositories.models import MonitoringTier, Repository

from .models import RepositorySnapshot


@dataclass(frozen=True)
class GrowthSignals:
    star_growth_1d: int | None
    star_growth_7d: int | None
    star_growth_30d: int | None
    fork_growth_7d: int | None
    fork_growth_30d: int | None


@dataclass(frozen=True)
class MonitoringAssessment:
    tier: MonitoringTier
    priority_score: int
    reasons: tuple[str, ...]


MONITORING_ALGORITHM_VERSION = "monitoring-priority-v1.1.0"


def observed_snapshot_span_days(repository: Repository) -> int:
    observed = repository.snapshots.filter(data_origin="OBSERVED")
    first = observed.order_by("snapshot_at").values_list("snapshot_at", flat=True).first()
    latest = observed.order_by("-snapshot_at").values_list("snapshot_at", flat=True).first()
    if first is None or latest is None:
        return 0
    return max(0, (latest - first).days)


def _delta(repository: Repository, field: str, days: int) -> int | None:
    snapshots = repository.snapshots.filter(data_origin="OBSERVED")
    latest = snapshots.order_by("-snapshot_at").first()
    if latest is None or getattr(latest, field) is None:
        return None
    cutoff = latest.snapshot_at - timedelta(days=days)
    baseline = snapshots.filter(snapshot_at__lte=cutoff).order_by("-snapshot_at").first()
    if baseline is None or getattr(baseline, field) is None:
        return None
    return getattr(latest, field) - getattr(baseline, field)


def growth_signals(repository: Repository) -> GrowthSignals:
    return GrowthSignals(
        star_growth_1d=_delta(repository, "stars", 1),
        star_growth_7d=_delta(repository, "stars", 7),
        star_growth_30d=_delta(repository, "stars", 30),
        fork_growth_7d=_delta(repository, "forks", 7),
        fork_growth_30d=_delta(repository, "forks", 30),
    )


def assess_monitoring_priority(repository: Repository, *, now=None) -> MonitoringAssessment:
    now = now or timezone.now()
    if repository.is_archived or repository.is_disabled:
        return MonitoringAssessment(MonitoringTier.ARCHIVED, 0, ("ARCHIVED_OR_DISABLED",))

    from apps.datasets.models import RepositoryPoolStatus, RepositoryPoolType
    from apps.forecasts.models import ModelStatus
    from apps.watchlists.models import WatchlistItem

    age_days = max(0, (now - repository.github_created_at).days)
    observed_span_days = observed_snapshot_span_days(repository)
    sampling_protected = observed_span_days < settings.MONITORING_MIN_OBSERVED_DAYS
    signals = growth_signals(repository)
    pushed_days = None
    if repository.github_pushed_at is not None:
        pushed_days = max(0, (now - repository.github_pushed_at).days)

    score = 20
    reasons: list[str] = []
    watchlisted = WatchlistItem.objects.filter(repository=repository).exists()
    training_protected = repository.dataset_pool_memberships.filter(
        pool__pool_type=RepositoryPoolType.TRAINING,
        pool__status=RepositoryPoolStatus.CONFIRMED,
    ).exists()
    activity = repository.activity_metrics.order_by("-metric_date").first()
    trend = repository.trend_scores.order_by("-calculated_at").first()
    potential = repository.potential_scores.order_by("-calculated_at").first()
    active_forecast = (
        repository.forecasts.filter(model__status=ModelStatus.ACTIVE)
        .order_by("-sample_at", "-id")
        .first()
    )

    if watchlisted:
        score += 60
        reasons.append("USER_WATCHLIST")
    if training_protected:
        score += 10
        reasons.append("CONFIRMED_TRAINING_POOL")
    if sampling_protected:
        reasons.append("OBSERVED_HISTORY_ACCUMULATING")
    if age_days <= 7:
        score += 35
        reasons.append("NEW_REPOSITORY")
    high_observed_growth = (signals.star_growth_1d or 0) >= 50 or (
        signals.star_growth_7d or 0
    ) >= 200
    rising_observed_growth = (signals.star_growth_7d or 0) >= 25 or (
        signals.fork_growth_7d or 0
    ) >= 10
    if high_observed_growth:
        score += 60
        reasons.append("HIGH_OBSERVED_GROWTH")
    elif rising_observed_growth:
        score += 35
        reasons.append("RISING_OBSERVED_GROWTH")

    active_development = False
    low_development = False
    recent_release = False
    if activity is not None:
        active_development = any(
            value is not None and value >= threshold
            for value, threshold in (
                (activity.commits_30d, 50),
                (activity.prs_created_30d, 20),
                (activity.active_contributors_30d, 5),
            )
        )
        if active_development:
            score += 20
            reasons.append("ACTIVE_DEVELOPMENT")
        required_low_activity = (
            activity.commits_30d,
            activity.prs_created_30d,
            activity.active_contributors_30d,
            activity.releases_30d,
        )
        low_development = all(value is not None for value in required_low_activity) and (
            activity.commits_30d <= settings.MONITORING_LOW_COMMITS_30D
            and activity.prs_created_30d <= settings.MONITORING_LOW_PRS_30D
            and activity.active_contributors_30d
            <= settings.MONITORING_LOW_CONTRIBUTORS_30D
        )
        recent_release = activity.releases_30d is not None and activity.releases_30d > 0
        if recent_release:
            score += 8
            reasons.append("RECENT_RELEASE")
    if pushed_days is not None and pushed_days <= 7:
        score += 15
        reasons.append("RECENT_PUSH")
    elif pushed_days is not None and pushed_days <= 30:
        score += 8
        reasons.append("PUSH_WITHIN_30D")
    elif pushed_days is None or pushed_days >= 180:
        score -= 25
        reasons.append("LONG_TERM_INACTIVE")

    high_trend = trend is not None and trend.trend_score is not None and trend.trend_score >= 80
    if high_trend:
        score += 15
        reasons.append("HIGH_TREND")
    high_potential = False
    if potential is not None and potential.potential_score is not None:
        if potential.confidence >= 0.55 and potential.potential_score >= 75:
            high_potential = True
            score += 15
            reasons.append("HIGH_CONFIDENCE_POTENTIAL")
    model_priority = False
    if active_forecast is not None:
        if (
            active_forecast.predicted_activity_percentile is not None
            and active_forecast.predicted_activity_percentile >= 80
        ):
            score += 60
            model_priority = True
            reasons.append("ACTIVE_MODEL_HIGH_PERCENTILE")
        elif (
            active_forecast.high_growth_probability is not None
            and active_forecast.high_growth_probability >= 0.8
        ):
            score += 60
            model_priority = True
            reasons.append("ACTIVE_MODEL_HIGH_GROWTH")

    low_observed_growth = (
        signals.star_growth_30d is not None
        and signals.fork_growth_30d is not None
        and signals.star_growth_30d <= settings.MONITORING_LOW_STAR_GROWTH_30D
        and signals.fork_growth_30d <= settings.MONITORING_LOW_FORK_GROWTH_30D
    )
    downsampling_eligible = all(
        (
            not sampling_protected,
            low_observed_growth,
            low_development,
            not watchlisted,
            not training_protected,
            not high_trend,
            not high_potential,
            not model_priority,
            not recent_release,
        )
    )
    if downsampling_eligible:
        reasons.append("LOW_VALUE_DOWNSAMPLING_ELIGIBLE")

    score = max(0, min(score, 100))
    if watchlisted or high_observed_growth:
        tier = MonitoringTier.HOT
    elif training_protected:
        tier = MonitoringTier.NORMAL
    elif age_days <= 7:
        tier = MonitoringTier.NEW
    elif score >= 75:
        tier = MonitoringTier.HOT
    elif rising_observed_growth or model_priority or score >= 65:
        tier = MonitoringTier.RISING
    elif downsampling_eligible and (pushed_days is None or pushed_days >= 180):
        tier = MonitoringTier.DORMANT
    elif downsampling_eligible:
        tier = MonitoringTier.STABLE
    else:
        tier = MonitoringTier.NORMAL
    return MonitoringAssessment(tier, score, tuple(reasons))


def determine_monitoring_tier(repository: Repository, *, now=None) -> MonitoringTier:
    return assess_monitoring_priority(repository, now=now).tier


def next_snapshot_time(tier: MonitoringTier, *, from_time=None):
    from_time = from_time or timezone.now()
    hours = settings.MONITORING_TIER_INTERVAL_HOURS[str(tier)]
    return from_time + timedelta(hours=hours)


def record_snapshot_schedule(repository_id: int, snapshot: RepositorySnapshot) -> MonitoringTier:
    repository = Repository.objects.get(pk=repository_id)
    tier = determine_monitoring_tier(repository, now=snapshot.snapshot_at)
    Repository.objects.filter(pk=repository_id).update(
        monitoring_tier=tier,
        monitoring_enabled=tier != MonitoringTier.ARCHIVED,
        last_snapshot_at=snapshot.snapshot_at,
        next_snapshot_at=next_snapshot_time(tier, from_time=snapshot.snapshot_at),
    )
    return tier


def refresh_repository_monitoring(repository_id: int, *, now=None) -> MonitoringAssessment:
    now = now or timezone.now()
    repository = Repository.objects.get(pk=repository_id)
    assessment = assess_monitoring_priority(repository, now=now)
    enabled = assessment.tier != MonitoringTier.ARCHIVED
    updates: dict[str, object] = {
        "monitoring_tier": assessment.tier,
        "monitoring_enabled": enabled,
    }
    if repository.monitoring_tier != assessment.tier or repository.next_snapshot_at is None:
        updates["next_snapshot_at"] = next_snapshot_time(assessment.tier, from_time=now)
    Repository.objects.filter(pk=repository_id).update(**updates)
    return assessment
