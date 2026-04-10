import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcribe_audio(file_path):
    """Groq Whisperを使って文字起こしを行う"""
    with open(file_path, "rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(file_path), file.read()),
            model="whisper-large-v3",
            response_format="text",
        )
    return transcription

def format_text_with_gemma(text):
    """Groq Gemmaを使って文字起こし結果を整形する"""
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
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "あなたは優秀な編集者です。文字起こしデータを読みやすく、構造的に整形する専門家です。"
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        model="gemma2-9b-it", # 最新の安定したGemmaモデルを使用
    )
    return chat_completion.choices[0].message.content

def process_audio(file_path):
    """文字起こしから整形までの一連の流れを実行"""
    print(f"Processing file: {file_path}")
    
    # 1. 文字起こし
    raw_text = transcribe_audio(file_path)
    print("Transcription complete.")
    
    # 2. 整形
    formatted_text = format_text_with_gemma(raw_text)
    print("Formatting complete.")
    
    return {
        "raw": raw_text,
        "formatted": formatted_text
    }
