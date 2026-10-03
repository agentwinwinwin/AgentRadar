import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.watchlists.models import Alert, AlertReceipt

from .test_services import repository


@pytest.mark.django_db
def test_watchlist_and_report_api_flow():
    repo = repository()
    client = APIClient()
    user = get_user_model().objects.create_user(username="api-owner", password="test-password")
    client.force_authenticate(user)
    first = client.post(reverse("watchlist"), {"repository_id": repo.id}, format="json")
    repeated = client.post(reverse("watchlist"), {"repository_id": repo.id}, format="json")
    assert first.status_code == 201 and repeated.status_code == 200
    assert client.get(reverse("watchlist")).json()["results"][0]["repository"]["id"] == repo.id
    detail = client.get(reverse("project-detail", kwargs={"repository_id": repo.id}))
    assert detail.json()["is_watchlisted"] is True
    report = client.post(reverse("report-list"), {"report_type": "DAILY"}, format="json")
    assert report.status_code == 201 and report.json()["content"]["llm_used"] is False
    assert (
        client.delete(reverse("watchlist-item", kwargs={"repository_id": repo.id})).status_code
        == 204
    )


@pytest.mark.django_db
def test_watchlist_alert_and_report_are_isolated_between_users():
    repo = repository()
    users = [
        get_user_model().objects.create_user(username=name, password="test-password")
        for name in ("alice", "bob")
    ]
    clients = [APIClient(), APIClient()]
    for client, user in zip(clients, users, strict=True):
        client.force_authenticate(user)

    assert clients[0].post(reverse("watchlist"), {"repository_id": repo.id}).status_code == 201
    assert clients[1].get(reverse("watchlist")).json()["results"] == []
    alert = Alert.objects.create(
        repository=repo,
        alert_type=Alert.Type.NEW_RELEASE,
        severity=Alert.Severity.INFO,
        title="release",
        evidence={"release_id": 1},
        detected_at=repo.created_at,
        rule_version="test",
        event_bucket="test",
    )
    AlertReceipt.objects.create(owner=users[0], alert=alert)
    assert len(clients[0].get(reverse("alert-list")).json()["results"]) == 1
    assert clients[1].get(reverse("alert-detail", kwargs={"alert_id": alert.id})).status_code == 404
    report = clients[0].post(reverse("report-list"), {"report_type": "DAILY"})
    assert report.status_code == 201
    assert (
        clients[1]
        .get(reverse("report-detail", kwargs={"report_id": report.json()["id"]}))
        .status_code
        == 404
    )
