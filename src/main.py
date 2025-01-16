from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from deep_translator import GoogleTranslator
import langdetect
from datetime import datetime
from typing import Optional
import boto3
import json

langdetect.DetectorFactory.seed = 0

app = FastAPI()

class TranslationRequest(BaseModel):
    text: str
    target_lang: str
    input_lang: Optional[str] = None

langs_dict = GoogleTranslator().get_supported_languages(as_dict=True)

def get_s3_client():
    '''
    Create and return a Boto3 S3 client.

    Args:
        None

    Returns:
        Boto3 S3 client object used to interact with AWS S3.
    '''
    return boto3.client('s3', region_name='eu-west-2')

def save_to_s3(data, bucket_name, key, s3_client):
    '''
    Save data to an AWS S3 bucket.
    
    Args:
        data (dict): The data to be saved to the S3 bucket.
        bucket (str): The name of the S3 bucket.
        key (str): The file name under which the data will be saved.
        s3_client (boto3.client): The Boto3 S3 client used to interact with AWS S3.
    
    Returns:
        None
    '''
    data_json = json.dumps(data)
    s3_client.put_object(Bucket=bucket_name,
                         Body=data_json,
                         Key=key)

def fetch_latest_id(bucket_name, s3_client):
    '''
    Fetch the latest unique ID number from files in an S3 bucket.
    
    Args:
        bucket_name (str): The name of the S3 bucket.
        s3_client (boto3.client): The Boto3 S3 client used to interact with AWS S3.
    
    Returns:
        int: The ID number of a file.
    '''
    objects = s3_client.list_objects_v2(Bucket=bucket_name)
    if 'Contents' not in objects:
        return 0
    last_modified = lambda obj: obj['LastModified']
    latest_key = [obj['Key'] for obj in sorted(objects['Contents'], key=last_modified)][-1]
    last_item = s3_client.get_object(
        Bucket=bucket_name, 
        Key=latest_key)['Body'].read()
    latest_id = json.loads(last_item)['id']
    return latest_id

@app.post("/translate/", status_code=201)
def translate_text(request: TranslationRequest, s3_client=Depends(get_s3_client)):
    '''
    Translate text from one language to another.

    This endpoint accepts text and a target language as input. The text is translated into the target language using Google Translate. Information about the translation is saved to an AWS S3 bucket.
        
    Args:
    request (TranslationRequest): A request body containing:
        - text (str): The text to be translated.
        - target_lang (str): The code of the target language.
        - input_lang (Optional[str]): The code of the input language (if not provided, this will be detected automatically).
    s3_client (boto3.client, optional): The Boto3 S3 client, injected as a dependency.
    
    Returns:
        dict: A JSON object containing:
            - original_text (str): The input text.
            - original_lang (str): The code of the input language, either specified or detected.
            - translated_text (str): The translated text.
            - output_lang (str): The code of the target language.
            - timestamp (str): The time when the translation was processed.
            - mismatch_detected (bool): Indicates whether a mismatch was found between the specified and automatically detected input languages.
    '''
    if request.target_lang.lower() not in [lang.lower() for lang in langs_dict.values()]:
        raise HTTPException(status_code=422, detail=f"Invalid language code: {request.target_lang}. Please check the list of supported languages.")

    if not request.text:
        raise HTTPException(status_code=422, detail='Empty input provided. Please try again.')

    try:
        detected_lang = langdetect.detect(request.text)
        if not detected_lang or len(detected_lang) != 2:
            raise HTTPException(status_code=422, detail='Input language could not be detected. Please try again.')
    except langdetect.lang_detect_exception.LangDetectException:
        raise HTTPException(status_code=422, detail='Input language could not be detected. Please try again.')

    try:
        translator = GoogleTranslator(source=detected_lang, target=request.target_lang.lower())
        translated_text = translator.translate(request.text)
    except ConnectionError:
        raise HTTPException(status_code=503, detail='Connection to translation service failed')
    except TimeoutError:
        raise HTTPException(status_code=504, detail='Translation request timed out')

    if request.text == translated_text:
        raise HTTPException(status_code=422, detail='Translation error. Inputted text was not recognised. Please try again.')

    input_lang = request.input_lang if request.input_lang else detected_lang

    latest_id = fetch_latest_id('translation_api_translations_bucket', s3_client)

    translation_info = {
        "id": latest_id+1,
        "original_text": request.text, 
        "original_lang": input_lang, 
        "translated_text": translated_text,
        "output_lang": request.target_lang.lower(),
        "timestamp": datetime.now().isoformat(),
        "mismatch_detected": False
        }
    
    if request.input_lang and request.input_lang != detected_lang:
        translation_info["mismatch_detected"] = True

    save_to_s3(translation_info, 'translation_api_translations_bucket', translation_info['timestamp'], s3_client)
        
    return translation_info

@app.get("/languages/", status_code=201)
def get_languages():
    '''
    This endpoint provides a list of languages supported by the translation API.
        
    Args:
        None
    
    Returns:
        dict: A JSON object containing the unique language codes and language names for all supported languages.
    '''
    langs_dict = GoogleTranslator().get_supported_languages(as_dict=True)
    return {'languages': langs_dict}

@app.get("/translations/")
def get_translations():
    
    return {'translations': []}


@app.exception_handler(RuntimeError)
def handle_runtime_errors(request: Request, exc: RuntimeError):
    '''
    Handles RuntimeError exceptions raised during API execution.

    The exception handler is triggered whenever a RuntimeError occurs. It returns a standardised error response with a 500 status code.

    Args:
        request (Request): The HTTP request that caused the exception.
        exc (RuntimeError): The RuntimeError instance that was raised.
    
    Returns:
        JSONResponse: A JSON response containing the following information:
            - detail (str): A message indicating that an unexpected error occurred.
    '''
    return JSONResponse (
		status_code=500,
		content={'detail':"An unexpected error occurred"})