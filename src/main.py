from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from deep_translator import GoogleTranslator
import langdetect
from datetime import datetime
from typing import Optional


langdetect.DetectorFactory.seed = 0

app = FastAPI()

class TranslationRequest(BaseModel):
    text: str
    target_lang: str
    input_lang: Optional[str] = None

langs_dict = GoogleTranslator().get_supported_languages(as_dict=True)

@app.post("/translate/", status_code=201)
def translate_text(request: TranslationRequest):
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

    translation_info = {
        "original_text": request.text, 
        "original_lang": input_lang, 
        "translated_text": translated_text,
        "output_lang": request.target_lang.lower(),
        "timestamp": datetime.now().isoformat(),
        "mismatch_detected": False
        }
    
    if request.input_lang and request.input_lang != detected_lang:
        translation_info["mismatch_detected"] = True
        
    return translation_info

@app.get("/languages/", status_code=201)
def get_languages():
    langs_dict = GoogleTranslator().get_supported_languages(as_dict=True)
    return {'languages': langs_dict}

@app.exception_handler(RuntimeError)
def handle_runtime_errors(request: Request, exc: RuntimeError):
	return JSONResponse (
		status_code=500,
		content={'detail':"An unexpected error occurred"})