import os
import google.generativeai as genai
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Groq client for Whisper
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

def format_text_with_gemini_stream(text):
    """Google Gemini API (Gemma 4) を使って文字起こし結果をストリーミング整形する"""
    gemini_key = os.getenv("GEMINI_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    if not gemini_key:
        yield "エラー: Gemini APIキーが設定されていません。"
        return
    
    try:
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
以下の文字起こしテキストを、読みやすい形式に整形してください。
- 文脈を維持しつつ、不要なフィラー（えー、あの、など）を削除してください。
- 誰が話しているか推測できる場合は、話者を分けて整理してください。
- 重要なポイントを箇条書きでまとめた「要約」を最後に付けてください。
- 自然な日本語に修正してください。

---
文字起こしテキスト:
{text}
---
"""
        response = model.generate_content(prompt, stream=True)
        for chunk in response:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        yield f"整形処理中にエラーが発生しました: {str(e)}"

def process_audio(file_path):
    """文字起こしから整形までの一連の流れを（非ストリームで）実行"""
    raw_text = transcribe_audio(file_path)
    
    # ストリーム用関数をリストで受け取って結合
    formatted_chunks = []
    for chunk in format_text_with_gemini_stream(raw_text):
        formatted_chunks.append(chunk)
    formatted_text = "".join(formatted_chunks)
    
    return {
        "raw": raw_text,
        "formatted": formatted_text
    }
