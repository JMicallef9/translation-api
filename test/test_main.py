from fastapi.testclient import TestClient
from src.main import app
import pytest
from unittest.mock import patch, MagicMock
from langdetect.lang_detect_exception import LangDetectException

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

	def test_invalid_target_lang_returns_error_message(self, test_client):
		response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "qq"})
		assert response.status_code == 422
		assert response.json() == {"detail": "Invalid language code: qq. Please check the list of supported languages."}
	
	def test_recognises_invalid_request_text(self, test_client):
		response = test_client.post("/translate/", json={"text": "zjxhakgdhgadshg", "target_lang": "de"})
		assert response.status_code == 422
		assert response.json() == {'detail': 'Translation error. Inputted text was not recognised. Please try again.'}

	def test_empty_input_returns_error_message(self, test_client):
		response = test_client.post("/translate/", json={"text": "", "target_lang": "de"})
		assert response.status_code == 422
		assert response.json() == {'detail': 'Empty input provided. Please try again.'}

	def test_language_code_detection_is_case_insensitive(self, test_client):
		response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "DE"})
		assert response.status_code == 201
		assert response.json()['output_lang'] == 'de'

	def test_mismatch_recorded_if_input_lang_does_not_match_detected_lang(self, test_client):
		payload = {"text": "Hello world", "target_lang": "DE", "input_lang": "lt"}
		response = test_client.post("/translate/", json=payload)
		assert response.json()['mismatch_detected']
	
	def test_handles_connection_error(self, test_client):
		payload = {"text": "Hello world", "target_lang": "de"}
		with patch("src.main.GoogleTranslator.translate", side_effect=ConnectionError):
			response = test_client.post("/translate/", json=payload)
		
		assert response.status_code == 503
		assert response.json() == {'detail': 'Connection to translation service failed'}
	
	def test_handles_timeout_error(self, test_client):
		payload = {"text": "Hello world", "target_lang": "de"}
		with patch("src.main.GoogleTranslator.translate", side_effect=TimeoutError):
			response = test_client.post("/translate/", json=payload)
		
		assert response.status_code == 504
		assert response.json() == {'detail': 'Translation request timed out'}
	
	def test_handles_runtime_errors(self, test_client):
		payload = {"text": "Hello world", "target_lang": "de"}
		with patch("src.main.GoogleTranslator.translate", side_effect=RuntimeError):
			response = test_client.post("/translate/", json=payload)
		
		assert response.status_code == 500
		assert response.json() == {'detail': 'An unexpected error occurred'}

	def test_exception_raised_if_lang_detection_fails(self, test_client):
		payload = {"text": "Hello world", "target_lang": "de"}
		with patch("src.main.langdetect.detect", return_value=""):
			response = test_client.post("/translate/", json=payload)	
		assert response.status_code == 422
		assert response.json() == {'detail': 'Input language could not be detected. Please try again.'}	
		with patch("src.main.langdetect.detect", return_value="deutsch"):
			response = test_client.post("/translate/", json=payload)
		assert response.status_code == 422
		assert response.json() == {'detail': 'Input language could not be detected. Please try again.'}	
		with patch("src.main.langdetect.detect", side_effect=LangDetectException("400", "test message")):
			response = test_client.post("/translate/", json=payload)
		assert response.status_code == 422
		assert response.json() == {'detail': 'Input language could not be detected. Please try again.'}	