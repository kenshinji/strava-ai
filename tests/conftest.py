import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient that skips DB initialization and the background scheduler."""
    with patch("app.main.init_db"), patch("app.main.scheduler"):
        with TestClient(app) as c:
            yield c


@pytest.fixture
def mock_openai_embeddings():
    """Mock openai.embeddings.create to return a fake embedding vector."""
    fake_embedding = [0.1] * 1536

    mock_data = MagicMock()
    mock_data.embedding = fake_embedding

    mock_response = MagicMock()
    mock_response.data = [mock_data]

    with patch("app.services.embedding.client") as mock_client:
        mock_client.embeddings.create.return_value = mock_response
        yield mock_client
