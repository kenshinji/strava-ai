import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient，跳过数据库初始化。"""
    with patch("app.main.init_db"):
        with TestClient(app) as c:
            yield c


@pytest.fixture
def mock_openai_embeddings():
    """Mock OpenAI embeddings.create，返回假向量。"""
    fake_embedding = [0.1] * 1536

    mock_data = MagicMock()
    mock_data.embedding = fake_embedding

    mock_response = MagicMock()
    mock_response.data = [mock_data]

    with patch("app.services.embedding.client") as mock_client:
        mock_client.embeddings.create.return_value = mock_response
        yield mock_client
