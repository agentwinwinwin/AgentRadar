import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.github.fakes import FakeGitHubClient
from apps.repositories.services import RepositoryService
from apps.repositories.tests.factories import github_repository_payload


@pytest.fixture
def repository(db):
    repository, _ = RepositoryService(FakeGitHubClient()).upsert_from_github(
        github_repository_payload(id=811_001, full_name="community/example", name="example")
    )
    return repository


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="community-user", password="safe-pass-123")


@pytest.mark.django_db
def test_like_requires_authentication_and_is_idempotent(repository, user):
    url = f"/api/v1/projects/{repository.id}/like"
    anonymous = APIClient()
    assert anonymous.post(url).status_code == 401

    client = APIClient()
    client.force_authenticate(user)
    first = client.post(url)
    repeated = client.post(url)

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.data["like_count"] == 1
    assert repeated.data["liked_by_me"] is True

    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 204
    assert anonymous.get(f"/api/v1/projects/{repository.id}/community").data["like_count"] == 0


@pytest.mark.django_db
def test_comments_are_public_to_read_but_authenticated_to_create(repository, user):
    comments_url = f"/api/v1/projects/{repository.id}/comments"
    community_url = f"/api/v1/projects/{repository.id}/community"
    anonymous = APIClient()

    assert anonymous.post(comments_url, {"content": "hello"}).status_code == 401

    client = APIClient()
    client.force_authenticate(user)
    created = client.post(comments_url, {"content": "  很有价值的项目  "})
    assert created.status_code == 201
    assert created.data["content"] == "很有价值的项目"

    public = anonymous.get(community_url)
    assert public.status_code == 200
    assert public.data["comment_count"] == 1
    assert public.data["comments"][0]["author"]["username"] == "community-user"
    assert public.data["liked_by_me"] is False

    comments = anonymous.get(comments_url)
    assert comments.status_code == 200
    assert comments.data["count"] == 1
    assert comments.data["results"][0]["content"] == "很有价值的项目"


@pytest.mark.django_db
def test_comments_from_different_users_are_publicly_visible(repository, user):
    second_user = get_user_model().objects.create_user(
        username="second-reviewer", password="safe-pass-456"
    )
    first_client = APIClient()
    first_client.force_authenticate(user)
    second_client = APIClient()
    second_client.force_authenticate(second_user)
    url = f"/api/v1/projects/{repository.id}/comments"

    assert first_client.post(url, {"content": "第一位用户的评论"}).status_code == 201
    assert second_client.post(url, {"content": "第二位用户的评论"}).status_code == 201

    public = APIClient().get(url)
    assert public.status_code == 200
    assert public.data["count"] == 2
    assert {item["author"]["username"] for item in public.data["results"]} == {
        "community-user",
        "second-reviewer",
    }


@pytest.mark.django_db
def test_comment_rejects_blank_and_oversized_content(repository, user):
    client = APIClient()
    client.force_authenticate(user)
    url = f"/api/v1/projects/{repository.id}/comments"

    assert client.post(url, {"content": "   "}).status_code == 400
    assert client.post(url, {"content": "x" * 2001}).status_code == 400
