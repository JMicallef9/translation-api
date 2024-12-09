from fastapi.testclient import TestClient
from src.main import app
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture()
def test_client():
	client = TestClient(app)
	return client

@pytest.fixture()
def de_translation_request(test_client):
	response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
	return response

@pytest.fixture()
def datetime_mock():
	with patch('src.main.datetime') as mock_dt:
		mock_now = MagicMock()
		mock_now.isoformat.return_value = 'mock_timestamp'
		mock_dt.now.return_value = mock_now
		yield mock_dt

class TestPostTranslate:
	def test_returns_201_status_code(self, de_translation_request):
		assert de_translation_request.status_code == 201
	
	def test_response_includes_original_and_translated_text(self, de_translation_request):
		assert de_translation_request.json()['original_text'] == 'Hello world'
		assert de_translation_request.json()['translated_text'] == 'Hallo Welt'

	def test_response_includes_original_and_target_langs(self, de_translation_request):
		assert de_translation_request.json()['original_lang'] == 'en'
		assert de_translation_request.json()['output_lang'] == 'de'

	def test_response_includes_timestamp(self, datetime_mock, test_client):
		response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		assert response.json()['timestamp'] == 'mock_timestamp'
	
	def test_invalid_target_lang_returns_error_message(self):
		response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "de"})

