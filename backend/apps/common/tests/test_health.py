import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_endpoint() -> None:
    response = APIClient().get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"service": "agentradar-backend", "status": "ok"}
