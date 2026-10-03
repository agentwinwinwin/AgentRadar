from apps.operations.models import RepositoryScoreHistory


def record_score_history(score, score_type: str) -> RepositoryScoreHistory:
    """Record observed calculations only; never synthesise historical rows."""
    calculated_at = score.calculated_at
    bucket_hour = calculated_at.hour - (calculated_at.hour % 6)
    history_bucket = f"{calculated_at:%Y%m%d}-{bucket_hour:02d}"
    value = (
        score.trend_score
        if score_type == RepositoryScoreHistory.ScoreType.TREND
        else score.potential_score
    )
    confidence = (
        score.data_completeness
        if score_type == RepositoryScoreHistory.ScoreType.TREND
        else score.confidence
    )
    history, _ = RepositoryScoreHistory.objects.update_or_create(
        repository=score.repository,
        score_type=score_type,
        algorithm_version=score.algorithm_version,
        history_bucket=history_bucket,
        defaults={
            "score": value,
            "confidence": confidence,
            "evidence": score.evidence,
            "calculated_at": calculated_at,
        },
    )
    return history
