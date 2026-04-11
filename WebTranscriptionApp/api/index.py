from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
import os
import json
import uuid
import sys
import traceback
import uvicorn

# Vercel環境で同じディレクトリのモジュール（processor.py）を読み込めるようにパスを追加
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# --- 診断用グローバル変数 ---
IMPORT_ERROR = None
processor = None

try:
    import processor
    print("SUCCESS: processor module imported successfully.")
except ImportError as e:
    IMPORT_ERROR = f"ImportError: {str(e)}\n{traceback.format_exc()}"
    print(f"CRITICAL: Failed to import processor: {IMPORT_ERROR}")
except Exception as e:
    IMPORT_ERROR = f"Unexpected Import Error: {str(e)}\n{traceback.format_exc()}"
    print(f"CRITICAL: Unexpected error during processor import: {IMPORT_ERROR}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ローカル環境対応のパス設定 ---
# Windows/Linux両対応のため、実行ファイルと同じ階層に temp_audio フォルダを作成して利用する
UPLOAD_DIR = os.path.join(current_dir, "temp_audio")
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_PAYLOAD_SIZE = 4.5 * 1024 * 1024  # 4.5MB

async def handle_transcribe(file: UploadFile):
    """文字起こし処理のメインロジック（完全非同期・詳細デバッグ付き）"""
    print(f"--- Request Start: {file.filename} ---")
    
    if processor is None:
        print(f"Error: Processor not loaded. {IMPORT_ERROR}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "ProcessorLoadError", "message": "モジュールの読み込みに失敗しました。", "details": IMPORT_ERROR}
        )

    try:
        content = await file.read()
        file_size = len(content)
        if file_size > MAX_PAYLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Payload Too Large (Max 4.5MB)")

        filename = file.filename if file.filename else "chunk.webm"
        ext = os.path.splitext(filename)[1] or ".webm"
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        print(f"Saving to {file_path} ({file_size} bytes)")
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        async def event_generator():
            try:
                print(f"Processing audio via processor.transcribe_audio: {file_path}")
                # 同期関数をスレッドプールで実行してイベントループをブロックしない
                raw_text = await run_in_threadpool(processor.transcribe_audio, file_path)
                print(f"Transcription received: {len(raw_text)} chars")
                
                if "エラー" in raw_text or "Error" in raw_text:
                    yield f"data: {json.dumps({'type': 'error', 'text': raw_text})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'raw', 'text': raw_text})}\n\n"
            except Exception as e:
                err_msg = f"Runtime Error: {str(e)}\n{traceback.format_exc()}"
                print(f"Generator Error: {err_msg}")
                yield f"data: {json.dumps({'type': 'error', 'text': err_msg})}\n\n"
            finally:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"Temp file deleted: {file_path}")
                except Exception as cleanup_err:
                    print(f"Cleanup error: {cleanup_err}")

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except HTTPException as he:
        raise he
    except Exception as e:
        trace = traceback.format_exc()
        print(f"Fatal Exception in handle_transcribe:\n{trace}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "InternalServerError", "message": str(e), "traceback": trace}
        )

# --- ルーティング設定 ---

@app.get("/")
async def read_index():
    """ルートアクセス時に index.html を返す（ローカル起動用）"""
    # プロジェクトルートの index.html を返す
    index_path = os.path.join(os.path.dirname(current_dir), "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "index.html not found", "path": index_path}

@app.post("/transcribe")
@app.post("/api/transcribe")
async def transcribe_root(file: UploadFile = File(...)):
    try:
        return await handle_transcribe(file)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        print(f"Unhandled exception in transcribe_root: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "UnhandledException", "message": str(e), "traceback": traceback.format_exc()}
        )

@app.post("/summarize")
@app.post("/api/summarize")
async def summarize_root(data: dict):
    if processor is None:
        raise HTTPException(status_code=500, detail={"error": "ProcessorLoadError", "details": IMPORT_ERROR})
    
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required for summarization")
    
    async def event_generator():
        try:
            # 同期ストリームを非同期に変換
            for chunk in await run_in_threadpool(lambda: list(processor.format_text_with_groq_stream(text))):
                yield f"data: {json.dumps({'type': 'formatted', 'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'Summarize Error: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/health")
@app.get("/health/")
@app.get("/api/health")
@app.get("/api/health/")
async def health_check():
    return {
        "status": "ok", 
        "processor_loaded": processor is not None, 
        "import_error": IMPORT_ERROR,
        "python_version": sys.version,
        "upload_dir": UPLOAD_DIR,
        "max_payload_size": MAX_PAYLOAD_SIZE
    }

if __name__ == "__main__":
    # ローカルで実行する場合のデフォルト設定
    uvicorn.run(app, host="0.0.0.0", port=8000)

async def handle_transcribe(file: UploadFile):
    """文字起こし処理のメインロジック（完全非同期・詳細デバッグ付き）"""
    print(f"--- Request Start: {file.filename} ---")
    
    if processor is None:
        print(f"Error: Processor not loaded. {IMPORT_ERROR}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "ProcessorLoadError", "message": "モジュールの読み込みに失敗しました。", "details": IMPORT_ERROR}
        )

    try:
        content = await file.read()
        file_size = len(content)
        if file_size > MAX_PAYLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Payload Too Large (Max 4.5MB)")

        filename = file.filename if file.filename else "chunk.webm"
        ext = os.path.splitext(filename)[1] or ".webm"
        unique_filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        print(f"Saving to {file_path} ({file_size} bytes)")
        with open(file_path, "wb") as buffer:
            buffer.write(content)

        async def event_generator():
            try:
                print(f"Processing audio via processor.transcribe_audio: {file_path}")
                # 同期関数をスレッドプールで実行してイベントループをブロックしない
                raw_text = await run_in_threadpool(processor.transcribe_audio, file_path)
                print(f"Transcription received: {len(raw_text)} chars")
                
                if "エラー" in raw_text or "Error" in raw_text:
                    yield f"data: {json.dumps({'type': 'error', 'text': raw_text})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'raw', 'text': raw_text})}\n\n"
            except Exception as e:
                err_msg = f"Runtime Error: {str(e)}\n{traceback.format_exc()}"
                print(f"Generator Error: {err_msg}")
                yield f"data: {json.dumps({'type': 'error', 'text': err_msg})}\n\n"
            finally:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"Temp file deleted: {file_path}")
                except Exception as cleanup_err:
                    print(f"Cleanup error: {cleanup_err}")

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    except HTTPException as he:
        raise he
    except Exception as e:
        trace = traceback.format_exc()
        print(f"Fatal Exception in handle_transcribe:\n{trace}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "InternalServerError", "message": str(e), "traceback": trace}
        )

# --- ルーティング設定 ---

@app.post("/transcribe")
@app.post("/api/transcribe")
async def transcribe_root(file: UploadFile = File(...)):
    try:
        return await handle_transcribe(file)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        print(f"Unhandled exception in transcribe_root: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500, 
            detail={"error": "UnhandledException", "message": str(e), "traceback": traceback.format_exc()}
        )

@app.post("/summarize")
@app.post("/api/summarize")
async def summarize_root(data: dict):
    if processor is None:
        raise HTTPException(status_code=500, detail={"error": "ProcessorLoadError", "details": IMPORT_ERROR})
    
    text = data.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Text is required for summarization")
    
    async def event_generator():
        try:
            # 同期ストリームを非同期に変換
            for chunk in await run_in_threadpool(lambda: list(processor.format_text_with_groq_stream(text))):
                yield f"data: {json.dumps({'type': 'formatted', 'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'Summarize Error: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/health")
@app.get("/health/")
@app.get("/api/health")
@app.get("/api/health/")
async def health_check():
    return {
        "status": "ok", 
        "processor_loaded": processor is not None, 
        "import_error": IMPORT_ERROR,
        "python_version": sys.version,
        "upload_dir": UPLOAD_DIR,
        "max_payload_size": MAX_PAYLOAD_SIZE
    }
