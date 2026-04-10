import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Groq client for Whisper
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcribe_audio(file_path):
    """Groq Whisperを使って文字起こしを行う"""
    try:
        with open(file_path, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(os.path.basename(file_path), file.read()),
                model="whisper-large-v3",
                response_format="text",
            )
        return transcription
    except Exception as e:
        return f"文字起こしエラー: {str(e)}"

def process_audio(file_path):
    """文字起こしを実行し、結果を返す"""
    raw_text = transcribe_audio(file_path)
    
    return {
        "raw": raw_text,
        "formatted": raw_text  # 整形せずそのまま返す
    }
