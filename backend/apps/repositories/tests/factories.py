def github_repository_payload(**overrides):
    payload = {
        "id": 123,
        "node_id": "R_repo",
        "owner": {"id": 10, "login": "example"},
        "name": "browser-agent",
        "full_name": "example/browser-agent",
        "description": "A browser agent framework",
        "homepage": "https://example.test",
        "private": False,
        "visibility": "public",
        "fork": False,
        "archived": False,
        "disabled": False,
        "size": 100,
        "stargazers_count": 42,
        "forks_count": 5,
        "subscribers_count": 3,
        "open_issues_count": 7,
        "language": "Python",
        "topics": ["Browser-Agent", "AI-Agent"],
        "license": {"key": "mit", "spdx_id": "MIT"},
        "default_branch": "main",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2026-08-15T00:00:00Z",
        "pushed_at": "2026-08-14T00:00:00Z",
    }
    payload.update(overrides)
    return payload
