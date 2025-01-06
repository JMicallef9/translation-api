import pytest
from moto import mock_aws
import boto3
from src.s3_utils import save_to_s3
import json

@pytest.fixture()
def s3_mock():
    with mock_aws():
        s3 = boto3.client('s3', region_name='eu-west-2')
        s3.create_bucket(Bucket='test_bucket',
                         CreateBucketConfiguration={
                            'LocationConstraint': 'eu-west-2'
                         })
        yield s3

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
        save_to_s3(dummy_request, s3_mock, 'test_bucket')

        object_list = s3_mock.list_objects_v2(Bucket='test_bucket')
        assert object_list['Contents'][0]['Key'] == '2015-01-27T05:57:31.399861+00:00'

    def test_object_body_contains_expected_data(self, s3_mock, dummy_request):
        save_to_s3(dummy_request, s3_mock, 'test_bucket')

        result = s3_mock.get_object(
            Bucket='test_bucket',
            Key='2015-01-27T05:57:31.399861+00:00')['Body'].read()

        assert json.loads(result) == dummy_request
