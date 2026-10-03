from celery import shared_task
from django.conf import settings

from apps.repositories.models import Repository

from .locks import RedisCapabilityLock
from .services import DataMaturityService


@shared_task(name="capabilities.evaluate_data_maturity")
def evaluate_data_maturity():
    with RedisCapabilityLock("data-maturity", ttl=3600) as lock:
        if not lock.acquired:
            return {"status": "SKIPPED", "reason": "evaluation_lock_busy"}
        result = DataMaturityService().evaluate()
    scoring_capabilities = {
        "STAR_GROWTH_7D",
        "STAR_GROWTH_30D",
        "FORK_GROWTH_7D",
        "FORK_GROWTH_30D",
        "MOMENTUM",
        "HYPE_RISK",
    }
    if scoring_capabilities.intersection(result["transitioned_to_ready"]):
        recalculate_mature_scores.delay()
        result["recalculation_dispatched"] = True
    else:
        result["recalculation_dispatched"] = False
    # Daily collection may make individual repositories eligible after the
    # activation rollout. Dispatching is cheap and idempotent: the ML task only
    # selects repositories without a frozen result for the ACTIVE model version.
    from apps.forecasts.models import MLModel, ModelStatus

    active_star_model = (
        MLModel.objects.filter(status=ModelStatus.ACTIVE, feature_version="feature-v2.0.0")
        .order_by("-activated_at", "-created_at")
        .first()
    )
    if active_star_model:
        from apps.forecasts.tasks import predict_newly_eligible_star_repositories

        predict_newly_eligible_star_repositories.delay(active_star_model.model_version)
        result["star_eligibility_prediction_dispatched"] = True
        result["star_model_version"] = active_star_model.model_version
    else:
        result["star_eligibility_prediction_dispatched"] = False
    return result


@shared_task(name="capabilities.recalculate_mature_scores")
def recalculate_mature_scores(after_id: int = 0):
    from apps.trends.tasks import dispatch_trend_score

    batch_size = settings.CAPABILITY_RECALC_BATCH_SIZE
    repository_ids = list(
        Repository.objects.filter(is_disabled=False, is_fork=False, id__gt=after_id)
        .order_by("id")
        .values_list("id", flat=True)[:batch_size]
    )
    for repository_id in repository_ids:
        dispatch_trend_score(repository_id)
    if len(repository_ids) == batch_size:
        recalculate_mature_scores.apply_async(args=[repository_ids[-1]], countdown=5)
    return {
        "dispatched": len(repository_ids),
        "after_id": after_id,
        "next_after_id": repository_ids[-1] if repository_ids else None,
        "has_more": len(repository_ids) == batch_size,
    }
