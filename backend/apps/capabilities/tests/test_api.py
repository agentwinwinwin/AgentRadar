import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from ..models import CapabilityName, CapabilityStatus, DataCapability


@pytest.mark.django_db
def test_operations_status_exposes_capability_reason_to_staff():
    now = timezone.now()
    DataCapability.objects.create(
        name=CapabilityName.MOMENTUM,
        status=CapabilityStatus.ACCUMULATING,
        data_coverage=0.25,
        reason="Growth history is still accumulating",
        metrics={"qualified_repositories": 5},
        last_evaluated_at=now,
    )
    staff = get_user_model().objects.create_user(username="operator", is_staff=True)
    client = APIClient()
    client.force_authenticate(staff)

    response = client.get("/api/v1/operations/status")

    assert response.status_code == 200
    assert response.data["capabilities"][0]["name"] == CapabilityName.MOMENTUM
    assert response.data["capabilities"][0]["status"] == CapabilityStatus.ACCUMULATING
    assert response.data["capabilities"][0]["coverage"] == 0.25
    assert "accumulating" in response.data["capabilities"][0]["reason"]
