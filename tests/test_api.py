import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from sqlalchemy.exc import OperationalError


class TestHealthEndpoint:
    """/health is a readiness probe: it must fail when the database is gone,
    otherwise Render keeps the service marked healthy while every data
    endpoint returns 500."""

    def test_health_ok_when_database_answers(self, client):
        with patch("app.main.engine", MagicMock()):
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}

    def test_health_returns_503_when_database_unreachable(self, client):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = OperationalError(
            "SELECT 1", {}, Exception("tenant/user not found")
        )
        with patch("app.main.engine", mock_engine):
            response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "degraded", "database": "unreachable"}

    def test_health_does_not_leak_connection_details(self, client):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = OperationalError(
            "SELECT 1", {}, Exception("could not connect to db.secret-host.supabase.com")
        )
        with patch("app.main.engine", mock_engine):
            response = client.get("/health")
        assert "secret-host" not in response.text

    def test_health_fails_when_query_fails(self, client):
        # Connecting can succeed while the server rejects the query.
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value.execute.side_effect = (
            OperationalError("SELECT 1", {}, Exception("server shutting down"))
        )
        with patch("app.main.engine", mock_engine):
            response = client.get("/health")
        assert response.status_code == 503


class TestChatEndpoint:
    @patch("app.api.chat.chat", new_callable=AsyncMock)
    def test_chat_success(self, mock_chat, client):
        mock_chat.return_value = "You ran 3 times last week, 15 km total."

        response = client.post(
            "/api/chat",
            json={"message": "How much did I run last week?", "session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "You ran 3 times last week, 15 km total."
        assert data["session_id"] == "test-session"
        mock_chat.assert_called_once_with(
            user_message="How much did I run last week?",
            chat_history=[],
        )

    @patch("app.api.chat.chat", new_callable=AsyncMock)
    def test_chat_with_history(self, mock_chat, client):
        mock_chat.return_value = "Sure, picking up where we left off."
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        response = client.post(
            "/api/chat",
            json={"message": "continue", "history": history},
        )

        assert response.status_code == 200
        mock_chat.assert_called_once_with(
            user_message="continue",
            chat_history=history,
        )

    @patch("app.api.chat.chat", new_callable=AsyncMock)
    def test_chat_server_error(self, mock_chat, client):
        mock_chat.side_effect = RuntimeError("OpenAI API down")

        response = client.post(
            "/api/chat",
            json={"message": "trigger an error"},
        )

        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

    @patch("app.api.chat.chat", new_callable=AsyncMock)
    def test_chat_error_does_not_leak_internals(self, mock_chat, client):
        """The real leak this replaces: a paused database made this endpoint
        hand every caller the DB host, its IP and the Supabase project ref."""
        mock_chat.side_effect = RuntimeError(
            'connection to server at "aws-1-eu-west-1.pooler.supabase.com" '
            "(54.247.26.119), port 5432 failed: FATAL: tenant/user "
            "postgres.ztxmcfytzdflgwykpasf not found"
        )

        response = client.post("/api/chat", json={"message": "hello"})

        assert response.status_code == 500
        for secret in ("pooler.supabase.com", "54.247.26.119", "ztxmcfytzdflgwykpasf"):
            assert secret not in response.text

    def test_chat_missing_message_returns_422(self, client):
        response = client.post("/api/chat", json={"session_id": "test"})
        assert response.status_code == 422

    def test_chat_default_session_id(self, client):
        with patch("app.api.chat.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "reply"

            response = client.post("/api/chat", json={"message": "Hello"})

            assert response.status_code == 200
            assert response.json()["session_id"] == "default"


class TestSyncEndpoint:
    @patch("app.main.run_sync", new_callable=AsyncMock)
    def test_sync_error_does_not_echo_upstream_response(self, mock_sync, client):
        # run_sync keeps the raw Strava payload out of its return value; this
        # pins that contract from the endpoint's side.
        mock_sync.return_value = {"status": "error", "message": "Token refresh failed"}

        response = client.post("/api/sync")

        assert response.status_code == 200
        assert response.json()["message"] == "Token refresh failed"


class TestRunSyncErrorHandling:
    def test_token_refresh_failure_keeps_payload_out_of_result(self):
        # asyncio.run rather than pytest-asyncio: one async test isn't worth
        # a new test dependency.
        from app.services.sync import run_sync

        upstream = {"message": "Bad Request", "errors": [{"field": "client_id"}]}
        with patch("app.services.sync.refresh_token", new_callable=AsyncMock) as mock_rt:
            mock_rt.return_value = upstream
            result = asyncio.run(run_sync())

        assert result == {"status": "error", "message": "Token refresh failed"}
        assert "client_id" not in str(result)
