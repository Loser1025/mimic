import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from api import processor

app = FastAPI()

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vercel環境では /tmp ディレクトリのみ書き込み可能
UPLOAD_DIR = "/tmp"

@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    try:
        # ファイルを一時保存
        file_path = os.path.join(UPLOAD_DIR, file.filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 文字起こしと整形処理を実行
        result = processor.process_audio(file_path)
        
        # 一時ファイルを削除
        os.remove(file_path)
        
        return result
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
