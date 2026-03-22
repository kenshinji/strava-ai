from unittest.mock import patch, AsyncMock


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestChatEndpoint:
    @patch("app.api.chat.chat", new_callable=AsyncMock)
    def test_chat_success(self, mock_chat, client):
        mock_chat.return_value = "你上周跑了3次，总共15公里。"

        response = client.post(
            "/api/chat",
            json={"message": "我上周跑了多少？", "session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "你上周跑了3次，总共15公里。"
        assert data["session_id"] == "test-session"
        mock_chat.assert_called_once_with(
            user_message="我上周跑了多少？",
            chat_history=[],
        )

    @patch("app.api.chat.chat", new_callable=AsyncMock)
    def test_chat_with_history(self, mock_chat, client):
        mock_chat.return_value = "好的，继续上次的话题。"
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"},
        ]

        response = client.post(
            "/api/chat",
            json={"message": "继续", "history": history},
        )

        assert response.status_code == 200
        mock_chat.assert_called_once_with(
            user_message="继续",
            chat_history=history,
        )

    @patch("app.api.chat.chat", new_callable=AsyncMock)
    def test_chat_server_error(self, mock_chat, client):
        mock_chat.side_effect = RuntimeError("OpenAI API down")

        response = client.post(
            "/api/chat",
            json={"message": "测试错误"},
        )

        assert response.status_code == 500
        assert "OpenAI API down" in response.json()["detail"]

    def test_chat_missing_message_returns_422(self, client):
        response = client.post("/api/chat", json={"session_id": "test"})
        assert response.status_code == 422

    def test_chat_default_session_id(self, client):
        with patch("app.api.chat.chat", new_callable=AsyncMock) as mock_chat:
            mock_chat.return_value = "回复"

            response = client.post("/api/chat", json={"message": "你好"})

            assert response.status_code == 200
            assert response.json()["session_id"] == "default"
