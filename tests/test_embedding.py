from unittest.mock import patch, MagicMock, call
from app.services.embedding import get_embedding, embed_all_activities


class TestGetEmbedding:
    def test_returns_vector(self, mock_openai_embeddings):
        result = get_embedding("测试文本")
        assert isinstance(result, list)
        assert len(result) == 1536
        mock_openai_embeddings.embeddings.create.assert_called_once()

    def test_calls_correct_model(self, mock_openai_embeddings):
        get_embedding("hello")
        call_kwargs = mock_openai_embeddings.embeddings.create.call_args
        assert call_kwargs.kwargs["input"] == "hello"
        assert "model" in call_kwargs.kwargs


class TestEmbedAllActivities:
    @patch("app.services.embedding.SessionLocal")
    def test_skips_when_no_activities(self, mock_session_cls, mock_openai_embeddings, capsys):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.all.return_value = []

        embed_all_activities()

        mock_openai_embeddings.embeddings.create.assert_not_called()
        mock_db.close.assert_called_once()
        output = capsys.readouterr().out
        assert "0 条" in output

    @patch("app.services.embedding.SessionLocal")
    def test_processes_batch_and_commits(self, mock_session_cls, mock_openai_embeddings):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        fake_activities = []
        for i in range(3):
            a = MagicMock()
            a.description_text = f"跑步记录 {i}"
            a.embedding = None
            fake_activities.append(a)

        mock_db.query.return_value.filter.return_value.all.return_value = fake_activities

        fake_data = []
        for _ in range(3):
            d = MagicMock()
            d.embedding = [0.5] * 1536
            fake_data.append(d)

        mock_response = MagicMock()
        mock_response.data = fake_data
        mock_openai_embeddings.embeddings.create.return_value = mock_response

        embed_all_activities()

        mock_openai_embeddings.embeddings.create.assert_called_once()
        mock_db.commit.assert_called_once()
        for a in fake_activities:
            assert a.embedding == [0.5] * 1536
        mock_db.close.assert_called_once()
