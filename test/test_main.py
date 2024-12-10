from fastapi.testclient import TestClient
from src.main import app

class TestPostTranslate:
	def test_returns_201_status_code(self):
		client = TestClient(app)
		response = client.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		assert response.status_code == 201
		assert response.json()['original_text'] == 'Hello world'
		assert response.json()['translated_text'] == 'Hallo Welt'
