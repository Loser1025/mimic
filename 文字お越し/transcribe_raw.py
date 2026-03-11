"""
STEP 1: 文字起こしのみ（話者分離・整形なし）
Groq Whisper で音声をそのままテキスト化して保存する。

出力したテキストをClaudeに渡すことで、内容の特徴に合ったプロンプトを設計できる。

使い方:
    python step1_transcribe_only.py <ファイルパス>

例:
    python step1_transcribe_only.py "C:/Users/you/Desktop/zoom_training.mp4"
    python step1_transcribe_only.py recording.mp4 --output raw_transcript.txt
"""

import os
import sys
import argparse
import tempfile
from pathlib import Path

TEMP_DIR = tempfile.gettempdir()

# Windows環境での文字化け対策
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ffmpegのパスをPATHに追加
_FFMPEG_BIN = r"C:\Users\弁護士法人響\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
if os.path.isdir(_FFMPEG_BIN) and _FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

from pydub import AudioSegment
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHUNK_LENGTH_MIN = 4

DOWNLOADS_DIR = Path.home() / "Downloads"


def extract_audio(video_path: str) -> tuple[str, bool]:
    """mp4なら音声抽出してmp3に変換。それ以外はそのまま返す。"""
    ext = Path(video_path).suffix.lower()
    if ext == ".mp4":
        print(f"\n🎬 MP4から音声を抽出しています...")
        out_path = str(Path(video_path).with_suffix("")) + "_audio.mp3"
        audio = AudioSegment.from_file(video_path, format="mp4")
        audio.export(out_path, format="mp3")
        print(f"   音声ファイルを作成: {out_path}")
        return out_path, True  # True = 一時ファイルなので後で削除
    return video_path, False


def split_audio(audio_path: str, chunk_length_min: int) -> list[str]:
    """音声ファイルをチャンクに分割する（Groq 25MB制限対応）"""
    print(f"\n🔪 音声を{chunk_length_min}分ごとに分割しています...")
    audio = AudioSegment.from_file(audio_path)
    total_min = len(audio) / 1000 / 60
    print(f"   合計時間: {total_min:.1f}分 → {-(-int(total_min) // chunk_length_min)}チャンク予定")

    chunk_length_ms = chunk_length_min * 60 * 1000
    chunks = []
    for i, start_ms in enumerate(range(0, len(audio), chunk_length_ms)):
        chunk = audio[start_ms:start_ms + chunk_length_ms]
        chunk_path = os.path.join(TEMP_DIR, f"raw_chunk_{i}.mp3")
        chunk.export(chunk_path, format="mp3")
        chunks.append(chunk_path)
        print(f"   チャンク {i+1} 作成: {chunk_path}")

    print(f"✅ {len(chunks)} チャンクに分割しました。")
    return chunks


def transcribe_chunk(audio_path: str, client: Groq, chunk_index: int) -> str:
    """Whisperで1チャンクを文字起こし（LLM処理なし・生テキストのまま）"""
    print(f"  🎙️  Whisperで文字起こし中...")
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            language="ja",
            response_format="text"
        )
    text = str(result)
    print(f"  ✅ 完了（{len(text)}文字）")
    return text


def cleanup(chunk_files: list[str], temp_audio: str | None):
    """一時ファイルを削除"""
    for path in chunk_files:
        if os.path.exists(path):
            os.remove(path)
    if temp_audio and os.path.exists(temp_audio):
        os.remove(temp_audio)
    print("\n🗑️  一時ファイルを削除しました。")


def main():
    parser = argparse.ArgumentParser(description="STEP1: 文字起こしのみ（LLM処理なし）")
    parser.add_argument("video_file", help="動画・音声ファイルのパス（mp4/mp3/m4a等）")
    parser.add_argument("--output", default=None,
                        help="出力先テキストファイル（デフォルト: 入力ファイルと同じ場所・同じ名前.txt）")
    parser.add_argument("--chunk-min", type=int, default=CHUNK_LENGTH_MIN,
                        help=f"分割サイズ（分）（デフォルト: {CHUNK_LENGTH_MIN}）")
    args = parser.parse_args()
    if args.output is None:
        args.output = str(Path(args.video_file).with_suffix(".txt"))

    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY が設定されていません。")
        sys.exit(1)

    if not os.path.exists(args.video_file):
        print(f"❌ ファイルが見つかりません: {args.video_file}")
        sys.exit(1)

    print(f"✅ Groq APIキー確認済み")
    print(f"📂 処理ファイル: {args.video_file}")

    client = Groq(api_key=GROQ_API_KEY)

    audio_path, is_temp = extract_audio(args.video_file)
    chunk_files = split_audio(audio_path, args.chunk_min)

    transcript_parts = []
    failed_chunks = []

    for i, chunk_path in enumerate(chunk_files):
        print(f"\n{'='*50}")
        print(f"📍 チャンク {i+1}/{len(chunk_files)} を処理中...")
        try:
            text = transcribe_chunk(chunk_path, client, i)
            # チャンク番号をヘッダーとして付与（後でプロンプト設計の参考にしやすくするため）
            header = f"--- チャンク {i+1} ({args.chunk_min*(i)}分〜{args.chunk_min*(i+1)}分) ---"
            transcript_parts.append(f"{header}\n{text}")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            failed_chunks.append(i + 1)
            transcript_parts.append(f"--- チャンク {i+1} 処理失敗: {e} ---")

    cleanup(chunk_files, audio_path if is_temp else None)

    output_content = "\n\n".join(transcript_parts)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(f"\n{'='*50}")
    print(f"🎉 文字起こし完了！")
    if failed_chunks:
        print(f"⚠️  失敗チャンク: {failed_chunks}")
    print(f"✅ '{args.output}' に保存しました。")
    print()
    print("【次のステップ】")
    print(f"  生成された '{args.output}' の内容をClaudeに貼り付けて、")
    print("  プロンプトの設計を依頼してください。")


if __name__ == "__main__":
    main()
