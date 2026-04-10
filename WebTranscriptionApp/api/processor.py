import os
import google.generativeai as genai
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Groq client for Whisper transcription
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcribe_audio(file_path):
    """Groq Whisperを使って文字起こしを行う"""
    with open(file_path, "rb") as file:
        transcription = groq_client.audio.transcriptions.create(
            file=(os.path.basename(file_path), file.read()),
            model="whisper-large-v3",
            response_format="text",
        )
    return transcription

def format_text_with_gemini(text):
    """Google Gemini API (Gemma 4) を使って文字起こし結果を整形する"""
    gemini_key = os.getenv("GEMINI_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    if not gemini_key:
        return "エラー: GEMINI_KEY が設定されていません。"
    
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
以下の文字起こしテキストを、読みやすい形式に整形してください。
- 文脈を維持しつつ、不要なフィラー（えー、あの、など）を削除してください。
- 自然な日本語に修正してください。
- 適宜、見出しや箇条書きを用いて整理し、構造化してください。
- 最後に、内容の重要なポイントをまとめた「要約」を付けてください。

---
文字起こしテキスト:
{text}
---
"""
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"整形処理中にエラーが発生しました: {str(e)}"

def process_audio(file_path):
    """文字起こしから整形までの一連の流れを実行"""
    print(f"Processing file: {file_path}")
    
    # 1. 文字起こし
    raw_text = transcribe_audio(file_path)
    print("Transcription complete.")
    
    # 2. 整形 (Geminiを使用)
    formatted_text = format_text_with_gemini(raw_text)
    print("Formatting complete.")
    
    return {
        "raw": raw_text,
        "formatted": formatted_text
    }
