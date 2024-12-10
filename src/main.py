from fastapi import FastAPI
from pydantic import BaseModel
from deep_translator import GoogleTranslator

app = FastAPI()

class TranslationRequest(BaseModel):
    text: str
    target_lang: str

@app.post("/translate/", status_code=201)
def translate_text(request: TranslationRequest):
    translator = GoogleTranslator(target=request.target_lang)
    translated_text = translator.translate(request.text)
    return {"original_text": request.text, "translated_text": translated_text}