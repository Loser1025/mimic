# --- ライブラリのインポート ---
import os
import json
import base64
import requests
from pydub import AudioSegment
from dotenv import load_dotenv

# --- 事前準備：環境変数からAPIキーを読み込む ---
load_dotenv() # .envファイルの内容を環境変数として読み込む
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

def split_audio(audio_path, chunk_length_min=5):
    """
    長い音声ファイルを指定された分数（分）のチャンクに分割する関数
    """
    print(f"\n音声ファイルを{chunk_length_min}分ごとのチャンクに分割します...")
    try:
        audio = AudioSegment.from_file(audio_path)
    except FileNotFoundError:
        print(f"エラー: ファイルが見つかりません -> {audio_path}")
        return None
    
    chunk_length_ms = chunk_length_min * 60 * 1000
    chunks = []

    for i, start_ms in enumerate(range(0, len(audio), chunk_length_ms)):
        chunk = audio[start_ms:start_ms + chunk_length_ms]
        # ファイル形式を元ファイルの拡張子に合わせる
        original_extension = os.path.splitext(audio_path)[1]
        chunk_path = f"chunk_{i}{original_extension}"
        chunk.export(chunk_path, format=original_extension.replace('.', ''))
        chunks.append(chunk_path)
        print(f"  - チャンク {i+1} を作成しました: {chunk_path}")

    return chunks

def process_audio_chunk(audio_path, api_key):
    """
    単一の音声チャンクをGemini APIに送信し、文字起こしと整形を行う関数
    """
    if not api_key:
        return "エラー: Gemini APIキーが設定されていません。"

    # 音声ファイルを読み込み、Base64にエンコード
    try:
        with open(audio_path, "rb") as audio_file:
            audio_bytes = audio_file.read()
        encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")
        # ファイルの拡張子からMIMEタイプを判断
        ext = os.path.splitext(audio_path)[1].lower()
        if ext == ".mp3":
            mime_type = "audio/mpeg"
        elif ext == ".wav":
            mime_type = "audio/wav"
        elif ext == ".m4a":
            mime_type = "audio/m4a"
        else:
            return f"エラー: サポートされていないファイル形式です: {ext}"

    except Exception as e:
        return f"音声ファイル '{audio_path}' の読み込み中にエラー: {e}"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    prompt = f"""あなたは、音声認識と議事録整理の専門家です。添付された音声ファイルは、事務所の担当者とお客様の2名による会話の一部です。以下のタスクを厳密に実行してください:
1. 音声の内容を全て正確に文字起こししてください。
2. 文脈を判断し、話者を「【事務所】」「【お客様】」に区別してください。
3. 発言者が切り替わるごとに改行し、自然な対話形式の議事録を作成してください。
出力例:
---
【事務所】かしこまりました。
【お客様】はい、お願いします。
---
"""
    data = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": encoded_audio}}]}],
        "generationConfig": {"temperature": 0.2, "max_output_tokens": 8192}
    }

    try:
        print(f"  - APIにリクエストを送信中 ({os.path.basename(audio_path)})...")
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=600)
        response.raise_for_status()
        result = response.json()

        if 'candidates' in result and result['candidates'] and 'content' in result['candidates'][0] and 'parts' in result['candidates'][0]['content']:
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            finish_reason = result.get('candidates', [{}])[0].get('finishReason', 'UNKNOWN')
            return f"エラー: レスポンスにテキスト部分がありませんでした (理由: {finish_reason})"

    except requests.exceptions.RequestException as e:
        return f"APIリクエスト中にエラーが発生しました: {e}"
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        return f"APIレスポンスの解析中にエラーが発生しました: {e}\nResponse: {response.text}"

# --- メイン処理 ---
def main():
    """
    メインの処理を実行する関数
    """
    print("文字起こし処理を開始します...")

    if not GOOGLE_API_KEY or GOOGLE_API_KEY == "ここにあなたのAPIキーを貼り付けてください":
        print("エラー: .envファイルにGemini APIキーが設定されていません。")
        return

    # 1. ユーザーから音声ファイルのパスを入力してもらう
    audio_file_path = input("文字起こししたい音声ファイル名（例: meeting.mp3）を入力してください: ")

    # 2. 音声ファイルをチャンクに分割
    chunk_files = split_audio(audio_file_path, chunk_length_min=5)
    
    if chunk_files is None:
        print("処理を中断しました。")
        return

    full_transcript = []

    # 3. 各チャンクを処理
    for i, chunk_path in enumerate(chunk_files):
        print(f"\n--- チャンク {i+1}/{len(chunk_files)} ({chunk_path}) の処理を開始 ---")
        transcript_part = process_audio_chunk(chunk_path, GOOGLE_API_KEY)
        full_transcript.append(transcript_part)
        print(f"--- チャンク {i+1}/{len(chunk_files)} の処理が完了 ---")

    # 4. 一時ファイルをクリーンアップ
    for chunk_path in chunk_files:
        try:
            os.remove(chunk_path)
        except OSError as e:
            print(f"一時ファイル削除エラー: {e.strerror} - {e.filename}")
    print("\n一時チャンクファイルを削除しました。")

    # 5. 最終的な結果をMarkdownファイルに保存
    output_filename = f"transcript_{os.path.splitext(os.path.basename(audio_file_path))[0]}.md"
    output_content = f"# {audio_file_path} の文字起こし結果\n\n" + "\n".join(full_transcript)

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(output_content)

    print("\n\n--- 全ての処理が完了 ---")
    print(f"✅ 結果を '{output_filename}' に保存しました。")

if __name__ == "__main__":
    main()