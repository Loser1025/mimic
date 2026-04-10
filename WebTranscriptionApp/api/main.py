from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import json
from . import processor

app = FastAPI()

# CORS設定: 全てのオリジンを許可
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp"

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    # ファイルを一時保存
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    async def event_generator():
        try:
            # 1. 文字起こし (Groq Whisper) - 一括処理
            raw_text = processor.transcribe_audio(file_path)
            # 生の文字起こし結果を即座に送信
            yield f"data: {json.dumps({'type': 'raw', 'text': raw_text})}\n\n"
            
            # 2. 整形 (Gemini) - ストリーミング処理
            for chunk in processor.format_text_with_gemini_stream(raw_text):
                yield f"data: {json.dumps({'type': 'formatted', 'text': chunk})}\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
        finally:
            # 一時ファイルの削除
            if os.path.exists(file_path):
                os.remove(file_path)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
