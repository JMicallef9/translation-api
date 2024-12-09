from fastapi import FastAPI
from pydantic import BaseModel
from deep_translator import LingueeTranslator

app = FastAPI()

class TranslationRequest(BaseModel):
    text: str
    target_lang: str

@app.post("/translate/")
def translate_text(request: TranslationRequest):
    translator = DeeplTranslator(target=request.target_lang)
    translated_text = translator.translate(request.text)
    return {"original_text": request.text, "translated_text": translated_text}


translated_word = LingueeTranslator(source='english', target='german').translate('this flower smells nice')
# translated_text = translator.translate('This flower smells nice')
print(translated_word)