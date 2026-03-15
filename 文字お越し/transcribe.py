"""
Groq Whisper を使った音声文字起こし（VS Code / ローカル実行用）

使い方:
    python transcribe.py <音声ファイルパス>

例:
    python transcribe.py meeting.mp3
    python transcribe.py "C:/Users/you/Desktop/recording.m4a"
"""

import os
import sys
import json
import argparse
import tempfile
import time
from pathlib import Path

TEMP_DIR = tempfile.gettempdir()

# Windows環境での文字化け対策
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ffmpegのパスをPATHに追加（wingetでインストールした場合）
_FFMPEG_BIN = r"C:\Users\弁護士法人響\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
if os.path.isdir(_FFMPEG_BIN) and _FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

from pydub import AudioSegment
from groq import Groq, RateLimitError
from dotenv import load_dotenv

# .env ファイルからAPIキーを読み込む
load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHUNK_LENGTH_MIN = 3  # TPM制限(6000)を考慮し3分に短縮

DOWNLOADS_DIR = Path.home() / "Downloads"


def split_audio(audio_path, chunk_length_min=4):
    """音声ファイルをチャンクに分割する"""
    print(f"\n🔪 音声を{chunk_length_min}分ごとに分割しています...")
    audio = AudioSegment.from_file(audio_path)
    total_min = len(audio) / 1000 / 60
    print(f"   合計時間: {total_min:.1f}分")

    chunk_length_ms = chunk_length_min * 60 * 1000
    chunks = []

    for i, start_ms in enumerate(range(0, len(audio), chunk_length_ms)):
        chunk = audio[start_ms:start_ms + chunk_length_ms]
        chunk_path = os.path.join(TEMP_DIR, f"chunk_{i}.mp3")
        chunk.export(chunk_path, format="mp3")
        chunks.append(chunk_path)
        print(f"   チャンク {i+1} を作成: {chunk_path}")

    print(f"✅ 合計 {len(chunks)} チャンクに分割しました。")
    return chunks


def transcribe_with_groq(audio_path, client, previous_context=""):
    """
    Groq Whisper で文字起こし → テキストをGroq LLMで話者分離・整形
    previous_context: 前チャンクの末尾（話者の連続性を保つため）
    """
    print(f"\n  🎙️  Whisperで文字起こし中...")

    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            language="ja",
            response_format="text"
        )

    raw_text = transcription
    print(f"  ✅ 文字起こし完了（{len(raw_text)}文字）")
    print(f"  🤖 LLMで話者分離・整形中...")

    context_section = f"""【前チャンクの末尾】（話者の流れを引き継ぐために参照してください）
{previous_context}

""" if previous_context else ""

    prompt = f"""以下は、司法書士事務所の担当者とお客様の電話相談の文字起こしです（債務整理・借金返済の相談）。
2人の話者を正確に区別し、指定フォーマットで出力してください。

【事務所（担当者）の言葉の特徴】
- 「弊社」「かしこまりました」「お伺い」「ご案内」「ご状況」「ご返済」「ご収入」「お力添え」などの丁寧な敬語を使う
- 相手の状況を確認・整理する質問をする（「〜ですかね」「〜かなと思うんですけど」）
- 手続きの説明・解決策の提案をする（「弊社の方で〜」「今回〜の対応ができそうです」）
- 「なるほどですね」「そうなんですね」「かしこまりました」と応じる

【お客様の言葉の特徴】
- 借入先・金額・収入・生活費など自分の状況を説明する
- 「はい」「そうですね」「はいはい」などの短い相槌が多い
- 「自分が〜」「〜してて」「〜なんですけど」という話し言葉
- 「〜ですか？」「本当ですか？」と質問する

【話者判断の優先ルール】
1. 「弊社」を含む → 必ず【事務所】
2. 「かしこまりました」を含む → 必ず【事務所】
3. 「ありがとうございます」の直後に確認質問が続く → 【事務所】
4. 借入金額・会社名・月収など具体的な自分の情報を述べている → 【お客様】
5. 「はい」「そうですね」のみの短い発言 → 直前と異なる話者の相槌

{context_section}【出力フォーマット（厳守）】
必ず以下の形式で出力すること。【】タグと発言内容は同じ行に書く。【】タグの後に改行してはいけない。

【事務所】ここに発言内容を書く
【お客様】ここに発言内容を書く
【事務所】ここに発言内容を書く

※ 余計なコメント・説明・markdown記法は一切不要。上記フォーマットの行のみ出力する。

【文字起こし】
{raw_text}
"""

    # ------------------------------------------------------------
    # レート制限対策のリトライループ (8bモデルに切り替えて制限を緩和)
    # ------------------------------------------------------------
    max_retries = 3
    retry_delay = 10  # 待機時間を少し長めに設定
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=8192
            )
            raw_output = response.choices[0].message.content
            break
        except RateLimitError as e:
            if attempt < max_retries - 1:
                print(f"  ⚠️ レート制限に達しました。{retry_delay}秒待機してリトライします... ({attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # 指数バックオフ
            else:
                print(f"  ❌ レート制限エラーが解消されませんでした。")
                raise e
        except Exception as e:
            print(f"  ❌ 予期せぬエラーが発生しました: {e}")
            raise e

    # 【話者】\n発言 → 【話者】発言 に整形（LLMが改行を挟んだ場合の補正）
    import re
    formatted_text = re.sub(r'(【(?:事務所|お客様)】)\s*\n+\s*', r'\1', raw_output)

    print(f"  ✅ 話者分離・整形完了")
    return formatted_text


def cleanup_chunks(chunk_files):
    """一時チャンクファイルを削除"""
    for path in chunk_files:
        if os.path.exists(path):
            os.remove(path)
    print("\n🗑️  一時ファイルを削除しました。")


def main():
    parser = argparse.ArgumentParser(description="Groq Whisper 音声文字起こしツール")
    parser.add_argument("audio_file", help="文字起こしする音声ファイルのパス")
    parser.add_argument("--output", default=None, help="出力ファイル名（デフォルト: 入力ファイルと同じ場所・同じ名前.txt）")
    parser.add_argument("--chunk-min", type=int, default=CHUNK_LENGTH_MIN, help=f"分割サイズ（分）（デフォルト: {CHUNK_LENGTH_MIN}）")
    args = parser.parse_args()
    if args.output is None:
        args.output = str(Path(args.audio_file).with_suffix(".txt"))

    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY が設定されていません。")
        print("   .env ファイルに GROQ_API_KEY=your_key_here を記載してください。")
        sys.exit(1)

    audio_file_path = args.audio_file
    if not os.path.exists(audio_file_path):
        print(f"❌ ファイルが見つかりません: {audio_file_path}")
        sys.exit(1)

    print(f"✅ Groq APIキーを確認しました。")
    print(f"📂 処理するファイル: {audio_file_path}")

    client = Groq(api_key=GROQ_API_KEY)

    chunk_files = split_audio(audio_file_path, chunk_length_min=args.chunk_min)

    full_transcript = []
    failed_chunks = []
    previous_context = ""

    for i, chunk_path in enumerate(chunk_files):
        print(f"\n{'='*50}")
        print(f"📍 チャンク {i+1}/{len(chunk_files)} を処理中...")
        try:
            result = transcribe_with_groq(chunk_path, client, previous_context)
            full_transcript.append(result)
            # 次チャンクのために末尾5発言をコンテキストとして保持
            lines = [l for l in result.strip().splitlines() if l.strip()]
            previous_context = "\n".join(lines[-5:])
            
            # 連続リクエストによるレート制限を避けるため少し待機
            if i < len(chunk_files) - 1:
                time.sleep(2)
        except Exception as e:
            print(f"  ❌ エラーが発生しました: {e}")
            failed_chunks.append(i+1)
            full_transcript.append(f"<!-- チャンク{i+1} 処理失敗: {e} -->")

    cleanup_chunks(chunk_files)

    header = f"# {os.path.basename(audio_file_path)} の文字起こし結果\n\n"
    if failed_chunks:
        header += f"> ⚠️ チャンク {failed_chunks} の処理に失敗しました。\n\n"

    output_content = header + "\n\n---\n\n".join(full_transcript)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(f"\n{'='*50}")
    print(f"🎉 全処理完了！")
    if failed_chunks:
        print(f"⚠️  失敗チャンク: {failed_chunks}")
    print(f"✅ '{args.output}' に保存しました。")


if __name__ == "__main__":
    main()
