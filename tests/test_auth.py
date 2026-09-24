from __future__ import annotations

import pytest
from backend.models import User, UserSession


class TestAuthEndpoints:
    def test_register_success(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "teste@exemplo.com", "password": "senhaSegura123"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == "teste@exemplo.com"
        assert "id" in data["user"]

    def test_register_duplicate_email(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "duplicado@exemplo.com", "password": "senhaSegura123"},
        )
        response = client.post(
            "/api/auth/register",
            json={"email": "duplicado@exemplo.com", "password": "outraSenha456"},
        )
        assert response.status_code == 400
        assert "ja esta cadastrado" in response.json()["detail"]

    def test_register_short_password(self, client):
        response = client.post(
            "/api/auth/register",
            json={"email": "curto@exemplo.com", "password": "12"},
        )
        assert response.status_code == 422

    def test_login_success(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "login@exemplo.com", "password": "minhaSenha123"},
        )
        response = client.post(
            "/api/auth/login",
            json={"email": "login@exemplo.com", "password": "minhaSenha123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == "login@exemplo.com"

    def test_login_wrong_password(self, client):
        client.post(
            "/api/auth/register",
            json={"email": "errado@exemplo.com", "password": "senhaCorreta123"},
        )
        response = client.post(
            "/api/auth/login",
            json={"email": "errado@exemplo.com", "password": "senhaIncorreta"},
        )
        assert response.status_code == 401
        assert "Email ou senha incorretos" in response.json()["detail"]

    def test_login_nonexistent_user(self, client):
        response = client.post(
            "/api/auth/login",
            json={"email": "inexistente@exemplo.com", "password": "senhaQualquer"},
        )
        assert response.status_code == 401

    def test_me_success(self, client):
        reg = client.post(
            "/api/auth/register",
            json={"email": "me@exemplo.com", "password": "senhaSegura123"},
        )
        token = reg.json()["token"]

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == "me@exemplo.com"

    def test_me_unauthorized(self, client):
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_logout_invalidates_session(self, client):
        reg = client.post(
            "/api/auth/register",
            json={"email": "logout@exemplo.com", "password": "senhaSegura123"},
        )
        token = reg.json()["token"]

        # Logout
        logout_res = client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_res.status_code == 200
        assert "Logout realizado" in logout_res.json()["message"]

        # Verify token is now invalid
        me_res = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_res.status_code == 401

    def test_passwords_are_salted_and_hashed_in_db(self, client, db_session):
        raw_password = "superSecretPassword"
        client.post(
            "/api/auth/register",
            json={"email": "security@exemplo.com", "password": raw_password},
        )

        user = db_session.query(User).filter(User.email == "security@exemplo.com").first()
        assert user is not None
        assert user.password_hash != raw_password
        assert len(user.salt) > 0
        assert len(user.password_hash) == 64  # SHA-256 hex is 64 characters
