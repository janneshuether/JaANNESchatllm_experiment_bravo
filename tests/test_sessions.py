from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from backend.models import ChatMessage, ChatSession
from backend.services.sessions import (
    DEFAULT_SESSION_TITLE,
    create_session,
    generate_title,
    get_or_create_session,
    get_session_messages,
    list_sessions,
    update_session_title_if_default,
)


class TestSessionsService:
    def test_generate_title_clean_question(self):
        title = generate_title("Como fazer uma torta de maca?")
        assert "torta de maca" in title.lower() or "como fazer" in title.lower()
        assert len(title) <= 50

    def test_generate_title_removes_greetings(self):
        title = generate_title("Ola, me explica o que e um buraco negro no espaco?")
        assert "buraco negro" in title.lower()

    def test_generate_title_fallback_empty(self):
        title = generate_title("", "")
        assert title == DEFAULT_SESSION_TITLE

    def test_create_and_list_sessions(self, db_session):
        s1 = create_session(db_session, title="Primeira sessao")
        s2 = create_session(db_session, title="Segunda sessao")

        sessions = list_sessions(db_session)
        assert len(sessions) >= 2
        ids = [s.id for s in sessions]
        assert s1.id in ids
        assert s2.id in ids

    def test_session_messages_isolation(self, db_session):
        s1 = create_session(db_session)
        s2 = create_session(db_session)

        m1 = ChatMessage(session_key=s1.id, role="user", content="Msg para 1")
        m2 = ChatMessage(session_key=s2.id, role="user", content="Msg para 2")
        db_session.add_all([m1, m2])
        db_session.commit()

        msgs1 = get_session_messages(db_session, s1.id)
        msgs2 = get_session_messages(db_session, s2.id)

        assert len(msgs1) == 1
        assert msgs1[0].content == "Msg para 1"
        assert len(msgs2) == 1
        assert msgs2[0].content == "Msg para 2"

    def test_auto_title_update_if_default(self, db_session):
        session = create_session(db_session, title=DEFAULT_SESSION_TITLE)
        assert session.title == DEFAULT_SESSION_TITLE

        new_title = update_session_title_if_default(
            db_session, session, user_message="Receita de bolo de chocolate facil"
        )
        assert new_title != DEFAULT_SESSION_TITLE
        assert "bolo de chocolate" in new_title.lower()

        # Calling again should NOT overwrite the custom title
        second_title = update_session_title_if_default(
            db_session, session, user_message="Outra pergunta completamente diferente"
        )
        assert second_title == new_title


class TestSessionsEndpoints:
    def test_create_session_endpoint(self, client):
        response = client.post("/api/sessions", json={"title": "Meu Chat"})
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Meu Chat"
        assert "id" in data

    def test_list_sessions_endpoint(self, client):
        client.post("/api/sessions", json={"title": "Chat A"})
        client.post("/api/sessions", json={"title": "Chat B"})

        response = client.get("/api/sessions")
        assert response.status_code == 200
        titles = [s["title"] for s in response.json()]
        assert "Chat A" in titles
        assert "Chat B" in titles

    def test_get_session_messages_endpoint(self, client):
        res = client.post("/api/sessions", json={"title": "Com Mensagens"})
        sid = res.json()["id"]

        get_res = client.get(f"/api/sessions/{sid}/messages")
        assert get_res.status_code == 200
        assert get_res.json() == []

    def test_delete_session_endpoint(self, client):
        res = client.post("/api/sessions", json={"title": "Para deletar"})
        sid = res.json()["id"]

        del_res = client.delete(f"/api/sessions/{sid}")
        assert del_res.status_code == 200

        get_res = client.get(f"/api/sessions/{sid}/messages")
        assert get_res.status_code == 404

    @patch("backend.routers.chat.generate_reply", new_callable=AsyncMock)
    def test_chat_auto_generates_session_title(self, mock_reply, client):
        mock_reply.return_value = ("Esta e a resposta sobre astronomia.", "mock-model")

        # Create new session with default title
        sess_res = client.post("/api/sessions")
        sid = sess_res.json()["id"]
        assert sess_res.json()["title"] == DEFAULT_SESSION_TITLE

        # Send first message in this session
        chat_res = client.post(
            "/api/chat",
            json={
                "message": "Como funcionam as estrelas de neutrons?",
                "session_id": sid,
            },
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert data["session_id"] == sid
        assert data["session_title"] != DEFAULT_SESSION_TITLE
        assert "estrelas de neutrons" in data["session_title"].lower()

        # Messages must be saved in this session
        msgs_res = client.get(f"/api/sessions/{sid}/messages")
        assert msgs_res.status_code == 200
        assert len(msgs_res.json()) == 2
