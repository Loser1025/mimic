from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
import json
import processor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "/tmp"

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        async def event_generator():
            try:
                # 1. 生の文字起こしを実行
                raw_text = processor.transcribe_audio(file_path)
                yield f"data: {json.dumps({'type': 'raw', 'text': raw_text})}\n\n"
                
                # 2. 整形処理 (ライブ録音中の断片的な送信時は、要約まで行わずにrawだけ返すか、
                #    簡易的な整形を行う。ここではrawを優先)
                #- ライブモードの場合はここで終了し、最後に一括で /summarize を呼ぶ設計にする
                
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/summarize")
async def summarize(data: dict):
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required for summarization")
    
    async def event_generator():
        try:
            # Groq Llama 3 を使用してストリーミング返却
            for chunk in processor.format_text_with_groq_stream(text):
                yield f"data: {json.dumps({'type': 'formatted', 'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
