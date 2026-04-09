from unittest.mock import patch, AsyncMock


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


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
        assert "OpenAI API down" in response.json()["detail"]

    def test_chat_missing_message_returns_422(self, client):
        response = client.post("/api/chat", json={"session_id": "test"})
        assert response.status_code == 422

    def test_chat_default_session_id(self, client):
        with patch("app.api.chat.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "reply"

            response = client.post("/api/chat", json={"message": "Hello"})

            assert response.status_code == 200
            assert response.json()["session_id"] == "default"
