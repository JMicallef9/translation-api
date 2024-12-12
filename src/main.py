from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from deep_translator import GoogleTranslator
import langdetect
from datetime import datetime


langdetect.DetectorFactory.seed = 0

app = FastAPI()

class TranslationRequest(BaseModel):
    text: str
    target_lang: str

langs_dict = GoogleTranslator().get_supported_languages(as_dict=True)

@app.post("/translate/", status_code=201)
def translate_text(request: TranslationRequest):
    if request.target_lang not in langs_dict.values():
        raise HTTPException(status_code=422, detail=f"Invalid request. Language code {request.target_lang} is not recognised.")
    translator = GoogleTranslator(target=request.target_lang)
    translated_text = translator.translate(request.text)
    if request.text == translated_text:
        raise HTTPException(status_code=422, detail='Translation error. Inputted text was not recognised. Please try again.')
    return {
        "original_text": request.text, 
        "original_lang": langdetect.detect(request.text), 
        "translated_text": translated_text,
        "output_lang": request.target_lang,
        "timestamp": datetime.now().isoformat()
        }