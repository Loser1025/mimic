"""
ZOOM研修録画 (mp4/mp3/m4a) 文字起こし + サマリー生成ツール
Groq Whisper (音声認識) + Groq LLM (話者分離・整形) を使用

使い方:
    python transcribe_zoom.py <ファイルパス>

例:
    python transcribe_zoom.py "C:/Users/you/Desktop/zoom_training.mp4"
    python transcribe_zoom.py recording.mp4 --output report.md
    python transcribe_zoom.py recording.mp4 --no-summary
"""

import os
import sys
import re
import argparse
import tempfile
from pathlib import Path

# 一時ファイル用ASCIIパス
TEMP_DIR = tempfile.gettempdir()

# Windows環境での文字化け対策
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# ffmpegのパスをPATHに追加（wingetでインストールした場合）
_FFMPEG_BIN = r"C:\Users\弁護士法人響\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
if os.path.isdir(_FFMPEG_BIN) and _FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

from pydub import AudioSegment
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CHUNK_LENGTH_MIN = 4  # Groq Whisperの25MB制限に対応するため4分ごとに分割

DOWNLOADS_DIR = Path.home() / "Downloads"


# ============================================================
# プロンプト定義
# ============================================================

SPEAKER_SEPARATION_PROMPT = """以下はZOOM研修の録画を文字起こしした日本語テキストです。
研修には「講師（トレーナー・ファシリテーター）」と「参加者（受講者）」が登場します。
話者を正確に区別し、指定フォーマットで出力してください。

【講師の言葉の特徴】
- 研修内容の説明・解説・指導をする（「〜ということで」「〜のポイントは」「〜が大事です」「〜を意識してください」）
- 参加者に問いかける（「〜はどう思いますか？」「〜できていますか？」「〜を試してみましょう」）
- フィードバック・改善点を伝える（「〜がよかった」「〜をこうすると改善されます」「〜が課題ですね」）
- 話題の転換・進行をする（「では次に〜」「それでは〜」「続いて〜」「まとめると〜」）
- ロールプレイの設定・指示・振り返りをする（「〜という設定でやってみましょう」「今のはどうでしたか」）

【参加者の言葉の特徴】
- 相槌・受け答え（「はい」「なるほど」「ありがとうございます」「そうですね」）
- 自分の業務・状況を話す（「自分は〜しています」「〜のときに〜してしまいます」）
- 講師への質問（「〜はどういう意味ですか？」「〜はどうすればいいですか？」「〜のケースはどうしたらいいですか？」）
- ロールプレイで演じる（お客様役・営業役など）

【話者判断の優先ルール】
1. 研修内容の説明・解説・フィードバック → 【講師】
2. 「では」「次に」「ポイントは」「〜が大事」「〜を意識して」→ 【講師】
3. ロールプレイの設定・進行・振り返りの指示 → 【講師】
4. 「はい」「なるほど」のみの短い相槌 → 直前と異なる話者
5. 自分の業務状況・困りごとを説明している → 【参加者】
6. 「〜ですか？」「どうすれば〜」など質問している → 【参加者】

{context_section}【出力フォーマット（厳守）】
以下の形式のみで出力すること。【】タグと発言内容は必ず同じ行に書く。
余計なコメント・説明・markdown記法・空行の追加は一切禁止。

【出力例】
【講師】コンフォートゾーンというのはありとあらゆる領域で形成されます。
【参加者】なるほど、自分のパターンってあるんですね。
【講師】そうです。それがホメオスタシスの働きです。

【重要ルール】
- 上記の「出力例」の文章をそのまま出力してはいけない。必ず文字起こしの内容を出力すること。
- 発言内容が空のタグ（例：【講師】のみの行）は絶対に出力しないこと。
- 講師のみが話している区間は、【講師】タグだけで全て出力してよい。無理に【参加者】を作らないこと。
- 「はい」「そうですね」などの短い相槌のみ参加者の発言として扱う。

【文字起こし】
{raw_text}
"""

# ============================================================
# 処理関数
# ============================================================

def extract_audio_from_mp4(mp4_path: str) -> str:
    """mp4から音声を抽出してmp3として保存"""
    print(f"\n🎬 MP4から音声を抽出しています...")
    out_path = str(Path(mp4_path).with_suffix("")) + "_audio.mp3"
    audio = AudioSegment.from_file(mp4_path, format="mp4")
    audio.export(out_path, format="mp3")
    print(f"   音声ファイルを作成: {out_path}")
    return out_path


def split_audio(audio_path: str, chunk_length_min: int = CHUNK_LENGTH_MIN) -> list[str]:
    """音声ファイルをチャンクに分割する（Groq 25MB制限対応）"""
    print(f"\n🔪 音声を{chunk_length_min}分ごとに分割しています...")
    audio = AudioSegment.from_file(audio_path)
    total_min = len(audio) / 1000 / 60
    print(f"   合計時間: {total_min:.1f}分")

    chunk_length_ms = chunk_length_min * 60 * 1000
    chunks = []

    for i, start_ms in enumerate(range(0, len(audio), chunk_length_ms)):
        chunk = audio[start_ms:start_ms + chunk_length_ms]
        chunk_path = os.path.join(TEMP_DIR, f"zoom_chunk_{i}.mp3")
        chunk.export(chunk_path, format="mp3")
        chunks.append(chunk_path)
        print(f"   チャンク {i+1} を作成: {chunk_path}")

    print(f"✅ 合計 {len(chunks)} チャンクに分割しました。")
    return chunks


def transcribe_chunk(audio_path: str, client: Groq, previous_context: str = "") -> str:
    """
    1チャンクの文字起こし（Whisper）→ 話者分離・整形（LLM）
    previous_context: 前チャンクの末尾数行（話者の連続性を保つため）
    """
    print(f"\n  🎙️  Whisperで文字起こし中...")

    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=("audio.mp3", f),
            language="ja",
            response_format="text"
        )

    raw_text = str(transcription)
    print(f"  ✅ 文字起こし完了（{len(raw_text)}文字）")
    print(f"  🤖 LLMで話者分離・整形中...")

    context_section = (
        f"【前チャンクの末尾】（話者の流れを引き継ぐために参照してください）\n"
        f"{previous_context}\n\n"
        if previous_context else ""
    )

    prompt = SPEAKER_SEPARATION_PROMPT.format(
        context_section=context_section,
        raw_text=raw_text
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=8192
    )

    raw_output = response.choices[0].message.content

    # LLMが【話者】の後に改行を挟んだ場合を補正（次行が別タグの場合は改行を保持）
    formatted = re.sub(r'(【(?:講師|参加者)】)\s*\n+\s*(?!【)', r'\1', raw_output)

    # プロンプト例文がそのまま出力された行を除去
    formatted = re.sub(r'【(?:講師|参加者)】ここに発言内容を書く\n?', '', formatted)
    formatted = re.sub(r'【出力例】\n?', '', formatted)

    # 発言内容のない空タグ行を除去（【講師】のみ、または連続タグ）
    formatted = re.sub(r'^【(?:講師|参加者)】\s*$', '', formatted, flags=re.MULTILINE)
    formatted = re.sub(r'(?:【(?:講師|参加者)】){2,}', '', formatted)

    # 空行が連続している場合は1行に圧縮
    formatted = re.sub(r'\n{3,}', '\n\n', formatted).strip()

    print(f"  ✅ 話者分離・整形完了")
    return formatted




def cleanup_files(chunk_files: list[str], extracted_audio: str | None = None):
    """一時ファイルを削除"""
    targets = chunk_files + ([extracted_audio] if extracted_audio else [])
    for path in targets:
        if path and os.path.exists(path):
            os.remove(path)
    print("\n🗑️  一時ファイルを削除しました。")


# ============================================================
# メイン処理
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="ZOOM研修録画 文字起こしツール（mp4/mp3/m4a対応）"
    )
    parser.add_argument("video_file", help="文字起こしする動画・音声ファイルのパス")
    parser.add_argument(
        "--output",
        default=None,
        help="出力ファイル名（デフォルト: 入力ファイルと同じ場所・同じ名前.txt）"
    )
    parser.add_argument(
        "--chunk-min",
        type=int,
        default=CHUNK_LENGTH_MIN,
        help=f"分割サイズ（分）（デフォルト: {CHUNK_LENGTH_MIN}）"
    )
    args = parser.parse_args()
    if args.output is None:
        args.output = str(Path(args.video_file).with_suffix(".txt"))

    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY が設定されていません。")
        print("   .env ファイルに GROQ_API_KEY=your_key_here を記載してください。")
        sys.exit(1)

    video_path = args.video_file
    if not os.path.exists(video_path):
        print(f"❌ ファイルが見つかりません: {video_path}")
        sys.exit(1)

    print(f"✅ Groq APIキーを確認しました。")
    print(f"📂 処理するファイル: {video_path}")

    client = Groq(api_key=GROQ_API_KEY)

    # mp4の場合は先に音声を抽出
    extracted_audio = None
    if Path(video_path).suffix.lower() == ".mp4":
        extracted_audio = extract_audio_from_mp4(video_path)
        audio_for_split = extracted_audio
    else:
        audio_for_split = video_path

    chunk_files = split_audio(audio_for_split, chunk_length_min=args.chunk_min)

    transcript_parts = []
    failed_chunks = []
    previous_context = ""

    for i, chunk_path in enumerate(chunk_files):
        print(f"\n{'='*50}")
        print(f"📍 チャンク {i+1}/{len(chunk_files)} を処理中...")
        try:
            result = transcribe_chunk(chunk_path, client, previous_context)
            transcript_parts.append(result)
            # 次チャンクのコンテキストとして末尾5発言を保持
            lines = [l for l in result.strip().splitlines() if l.strip()]
            previous_context = "\n".join(lines[-5:])
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ❌ エラー: {e}")
            failed_chunks.append(i + 1)
            transcript_parts.append(f"<!-- チャンク{i+1} 処理失敗: {e} -->")

    cleanup_files(chunk_files, extracted_audio)

    full_transcript = "\n\n".join(transcript_parts)

    # 出力ファイルを組み立て（文字起こし全文のみ）
    if failed_chunks:
        warning = f"> ⚠️ チャンク {failed_chunks} の処理に失敗しました。\n\n"
        output_content = warning + full_transcript
    else:
        output_content = full_transcript

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output_content)

    print(f"\n{'='*50}")
    print(f"🎉 全処理完了！")
    if failed_chunks:
        print(f"⚠️  失敗チャンク: {failed_chunks}")
    print(f"✅ '{args.output}' に保存しました。")


if __name__ == "__main__":
    main()
