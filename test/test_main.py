from fastapi.testclient import TestClient
from src.main import app
import pytest
from unittest.mock import patch, MagicMock
from langdetect.lang_detect_exception import LangDetectException
from moto import mock_aws
import boto3
import json

@pytest.fixture()
def test_client():
	client = TestClient(app)
	return client

@pytest.fixture()
def s3_mock():
    with mock_aws():
        s3 = boto3.client('s3', region_name='eu-west-2')
        s3.create_bucket(Bucket='translation_api_translations_bucket',
                         CreateBucketConfiguration={
                            'LocationConstraint': 'eu-west-2'
                         })
        yield s3

@pytest.fixture()
def de_translation_request(test_client, s3_mock):
	with patch("src.main.get_s3_client", return_value=s3_mock):
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

	def test_response_includes_timestamp(self, datetime_mock, test_client, s3_mock):
		with patch("src.main.get_s3_client", return_value=s3_mock):
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

	def test_language_code_detection_is_case_insensitive(self, test_client, s3_mock):
		with patch("src.main.get_s3_client", return_value=s3_mock):
			response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "DE"})
		assert response.status_code == 201
		assert response.json()['output_lang'] == 'de'

	def test_mismatch_recorded_if_input_lang_does_not_match_detected_lang(self, test_client, s3_mock):
		payload = {"text": "Hello world", "target_lang": "DE", "input_lang": "lt"}
		with patch("src.main.get_s3_client", return_value=s3_mock):
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
	
	def test_data_saved_to_s3_bucket(self, s3_mock, test_client, datetime_mock):
		with patch("src.main.get_s3_client", return_value=s3_mock):
			response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		
		object_list = s3_mock.list_objects_v2(Bucket='translation_api_translations_bucket')

		assert object_list['Contents'][0]['Key'] == 'mock_timestamp'
		result = s3_mock.get_object(
				Bucket='translation_api_translations_bucket',
				Key='mock_timestamp')['Body'].read()
			
		assert json.loads(result)['original_text'] == 'Hello world'
		assert json.loads(result)['original_lang'] == 'en'
		assert json.loads(result)['translated_text'] == 'Hallo Welt'
		assert json.loads(result)['output_lang'] == 'de'
		assert json.loads(result)['timestamp'] == 'mock_timestamp'
		assert json.loads(result)['mismatch_detected'] == False



class TestGetLanguages:
    def test_returns_list_of_available_languages(self, test_client):
        response = test_client.get("/languages/")
        assert response.status_code == 201
        body = response.json()['languages'].items()
        for key, value in body:
            assert type(key) == str
            assert type(value) == str
            assert len(key) > len(value)
        assert len(body) > 40