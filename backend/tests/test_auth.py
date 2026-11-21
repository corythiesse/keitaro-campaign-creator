"""Optional shared-token authentication for the HTTP API."""

AUTH_HEADERS = {"X-API-Token": "secret-token"}


async def test_health_is_always_available(monkeypatch, client, main_app):
    monkeypatch.setattr(main_app.settings, "api_auth_token", "secret-token")

    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_api_requires_configured_token(monkeypatch, client, main_app):
    monkeypatch.setattr(main_app.settings, "api_auth_token", "secret-token")

    missing = await client.get("/api/campaigns")
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "UNAUTHORIZED"

    wrong = await client.get("/api/campaigns", headers={"X-API-Token": "wrong"})
    assert wrong.status_code == 401

    header = await client.get("/api/campaigns", headers=AUTH_HEADERS)
    assert header.status_code == 200

    bearer = await client.get(
        "/api/campaigns", headers={"Authorization": "Bearer secret-token"}
    )
    assert bearer.status_code == 200


async def test_non_api_path_is_not_auth_protected(monkeypatch, client, main_app):
    monkeypatch.setattr(main_app.settings, "api_auth_token", "secret-token")

    response = await client.get("/apifoo")

    assert response.status_code == 404
    assert response.json()["detail"] != "Не указан или неверный API-токен"


async def test_api_is_open_when_token_is_not_configured(monkeypatch, client, main_app):
    monkeypatch.setattr(main_app.settings, "api_auth_token", "")

    response = await client.get("/api/campaigns")

    assert response.status_code == 200
