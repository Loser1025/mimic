import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Groq client
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

def format_text_with_groq_stream(text):
    """Groq Llama 3 を使って文字起こし結果をストリーミング整形する"""
    if not os.getenv("GROQ_API_KEY"):
        yield "エラー: GROQ_API_KEYが設定されていません。"
        return

    try:
        # Llama 3 などの強力なモデルを使用して整形
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system", 
                    "content": "あなたは優秀な編集者です。文字起こしテキストを読みやすく整形してください。文脈を維持しつつ不要なフィラーを削除し、自然な日本語に修正してください。最後に重要なポイントを箇条書きで要約してください。"
                },
                {
                    "role": "user", 
                    "content": f"以下のテキストを整形してください:\n\n{text}"
                }
            ],
            stream=True,
        )
        for chunk in completion:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        yield f"整形処理中にエラーが発生しました: {str(e)}"

def process_audio(file_path):
    """文字起こしを実行し、結果を返す"""
    raw_text = transcribe_audio(file_path)
    
    # 非同期ストリームを同期的に処理して結合
    formatted_chunks = []
    for chunk in format_text_with_groq_stream(raw_text):
        formatted_chunks.append(chunk)
    formatted_text = "".join(formatted_chunks)
    
    return {
        "raw": raw_text,
        "formatted": formatted_text
    }
