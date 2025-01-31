from fastapi.testclient import TestClient
from src.main import app, save_to_s3, get_s3_client, fetch_latest_id
import pytest
from unittest.mock import patch, MagicMock
from langdetect.lang_detect_exception import LangDetectException
from moto import mock_aws
import boto3
import json
from botocore.exceptions import ClientError

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
def test_client_with_s3_mock(s3_mock):
	def override_get_s3_client():
		return s3_mock
	app.dependency_overrides[get_s3_client] = override_get_s3_client
	client = TestClient(app)
	yield client
	app.dependency_overrides.clear()

@pytest.fixture()
def test_client_with_error(mocker):
	mock_s3_client = mocker.MagicMock()
	error = {"Error":
		   {"Code": "AccessDenied",
	  		"Message": 'Access Denied'}}
	mock_s3_client.list_objects_v2.side_effect = ClientError(error, "ListObjectsV2")
	app.dependency_overrides[get_s3_client] = lambda: mock_s3_client
	client = TestClient(app)
	yield client
	app.dependency_overrides.clear()


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


@pytest.fixture()
def dummy_request():
    return {"original_text": 'Hello world', 
        "original_lang": 'en', 
        "translated_text": 'Hallo Welt',
        "output_lang": 'de',
        "timestamp": '2015-01-27T05:57:31.399861+00:00',
        "mismatch_detected": False
        }

class TestSaveToS3:
    def test_object_saved_to_s3_bucket(self, s3_mock, dummy_request):
        save_to_s3(dummy_request, 'translation_api_translations_bucket', dummy_request['timestamp'], s3_mock)

        object_list = s3_mock.list_objects_v2(Bucket='translation_api_translations_bucket')
        assert object_list['Contents'][0]['Key'] == '2015-01-27T05:57:31.399861+00:00'

    def test_object_body_contains_expected_data(self, s3_mock, dummy_request):
        save_to_s3(dummy_request, 'translation_api_translations_bucket', dummy_request['timestamp'], s3_mock)

        result = s3_mock.get_object(
            Bucket='translation_api_translations_bucket',
            Key='2015-01-27T05:57:31.399861+00:00')['Body'].read()

        assert json.loads(result) == dummy_request

class TestFetchLatestID:
	def test_returns_latest_id(self, test_client_with_s3_mock):
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "DE"})
		result = fetch_latest_id('translation_api_translations_bucket', get_s3_client())
		assert result == 1
		assert isinstance(result, int)
	
	def test_returns_zero_if_bucket_empty(self, s3_mock):
		result = fetch_latest_id('translation_api_translations_bucket', s3_mock)
		assert result == 0
	
	def test_fetches_latest_id_from_multiple_objects(self, test_client_with_s3_mock):
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "DE"})
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "fr"})
		result = fetch_latest_id('translation_api_translations_bucket', get_s3_client())
		assert result == 2
		assert isinstance(result, int)


class TestPostTranslate:
	def test_returns_201_status_code(self, de_translation_request):
		assert de_translation_request.status_code == 201

	def test_response_includes_original_and_translated_text(self, de_translation_request):
		assert de_translation_request.json()['original_text'] == 'Hello world'
		assert de_translation_request.json()['translated_text'] == 'Hallo Welt'

	def test_response_includes_original_and_target_langs(self, de_translation_request):
		assert de_translation_request.json()['original_lang'] == 'en'
		assert de_translation_request.json()['output_lang'] == 'de'

	def test_response_includes_timestamp(self, datetime_mock, test_client_with_s3_mock):
		response = test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		assert response.json()['timestamp'] == 'mock_timestamp'
	
	def test_invalid_target_lang_returns_error_message(self, test_client):
		response = test_client.post("/translate/", json={"text": "Hello world", "target_lang": "qq"})
		assert response.status_code == 422
		assert response.json() == {"detail": "Invalid language code: qq. Please check the list of supported languages."}
	
	def test_recognises_invalid_request_text(self, test_client_with_s3_mock):
		response = test_client_with_s3_mock.post("/translate/", json={"text": "!!!!!!!@@@@@@*****??????", "target_lang": "de"})
		assert response.status_code == 422
		assert response.json() == {'detail': 'Input language could not be detected. Please try again.'}

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
	
	def test_data_saved_to_s3_bucket(self, test_client_with_s3_mock, datetime_mock):
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		
		object_list = get_s3_client().list_objects_v2(Bucket='translation_api_translations_bucket')

		assert object_list['Contents'][0]['Key'] == '-mock_timestamp'
		result = get_s3_client().get_object(
				Bucket='translation_api_translations_bucket',
				Key='-mock_timestamp')['Body'].read()
			
		assert json.loads(result)['original_text'] == 'Hello world'
		assert json.loads(result)['original_lang'] == 'en'
		assert json.loads(result)['translated_text'] == 'Hallo Welt'
		assert json.loads(result)['output_lang'] == 'de'
		assert json.loads(result)['timestamp'] == 'mock_timestamp'
		assert json.loads(result)['mismatch_detected'] == False

	def test_posted_translation_has_unique_id(self, test_client_with_s3_mock):
		response = test_client_with_s3_mock.post("/translate/", json={"text": "magnificent adventures", "target_lang": "es"})
		assert response.status_code == 201
		assert response.json()['id'] == 1


class TestGetLanguages:
	def test_returns_list_of_available_languages(self, test_client):
		response = test_client.get("/languages/")
		assert response.status_code == 201
		assert isinstance(response.json(), dict)
		body = response.json()['languages'].items()
		for key, value in body:
			assert type(key) == str
			assert type(value) == str
			assert len(key) > len(value)
		assert len(body) > 40
	
	def test_request_made_to_invalid_endpoint(self, test_client):
		response = test_client.get("/langs/")
		assert response.status_code == 404

class TestGetTranslations:
	def test_request_returns_a_list(self, test_client_with_s3_mock):
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "fr"})
		response = test_client_with_s3_mock.get("/translations/")
		assert response.status_code == 200
		assert isinstance(response.json()['translations'], list)
		assert len(response.json()['translations']) == 2

	def test_returns_single_translation_dictionary(self, test_client_with_s3_mock):
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		response = test_client_with_s3_mock.get("/translations/")
		assert response.status_code == 200
		assert len(response.json()['translations']) == 1

	def test_returns_correct_data_from_single_dict(self, test_client_with_s3_mock, datetime_mock):
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		response = test_client_with_s3_mock.get("/translations/")
		assert response.json()['translations'] == [{
			"id": 1,
			'original_text': 'Hello world',
			"original_lang": 'en',
			'translated_text': 'Hallo Welt',
			'output_lang': 'de',
			'timestamp': 'mock_timestamp',
			'mismatch_detected': False}]

	def test_returns_message_if_no_translations(self, test_client_with_s3_mock):
		response = test_client_with_s3_mock.get("/translations/")
		assert response.status_code == 200
		assert response.json() == {'message': 'No translations found'}

	def test_get_translations_handles_client_error(self, test_client_with_error):		
		response = test_client_with_error.get("/translations/")
		assert response.status_code == 500
		assert response.json() == {"error": "Failed to list objects: An error occurred (AccessDenied) when calling the ListObjectsV2 operation: Access Denied"}
	
	def test_get_translations_returns_only_10_items_by_default(self, test_client_with_s3_mock):
		for _ in range(15):
			test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		response = test_client_with_s3_mock.get("/translations/")
		assert len(response.json()['translations']) == 10

	def test_returns_continuation_token_where_required(self, test_client_with_s3_mock):
		for _ in range(15):
			test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		response = test_client_with_s3_mock.get("/translations/")
		assert 'translations' in response.json().keys()
		assert 'next_page' in response.json().keys()
		assert isinstance(response.json()['next_page'], str)
	
	def test_most_recent_items_returned_first(self, test_client_with_s3_mock):
		for _ in range(10):
			test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "de"})
		test_client_with_s3_mock.post("/translate/", json={"text": "Hello world", "target_lang": "fr"})
		response = test_client_with_s3_mock.get("/translations/")
		assert response.json()['translations'][0]['output_lang'] == 'fr'


# check fetch latest ID util function
