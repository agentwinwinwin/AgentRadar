from unittest.mock import Mock, patch

from apps.watchlists.tasks import dispatch_alert_evaluation


def test_full_alert_scan_skips_when_scoring_queue_is_backlogged(settings):
    settings.ALERT_FULL_SCAN_BACKLOG_THRESHOLD = 1000
    redis = Mock()
    redis.llen.return_value = 1001

    with patch("apps.watchlists.tasks.Redis.from_url", return_value=redis):
        result = dispatch_alert_evaluation.run()

    assert result == {
        "dispatched": 0,
        "status": "SKIPPED_BACKLOG",
        "scoring_backlog": 1001,
    }
    redis.set.assert_not_called()


def test_full_alert_scan_is_globally_coalesced(settings):
    settings.ALERT_FULL_SCAN_BACKLOG_THRESHOLD = 1000
    settings.ALERT_FULL_SCAN_COALESCE_TTL_SECONDS = 82800
    redis = Mock()
    redis.llen.return_value = 0
    redis.set.return_value = False

    with patch("apps.watchlists.tasks.Redis.from_url", return_value=redis):
        result = dispatch_alert_evaluation.run()

    assert result["status"] == "SKIPPED_DUPLICATE"
    assert result["dispatched"] == 0
