"""
unilive/voice_mode.py
────────────────────────────────────────────────────────
Gemini Live API リアルタイム音声対話クライアント

起動方法:
  python voice_mode.py          # 音声モード
  python voice_mode.py --text   # テキストモード（デバッグ用）

必要ライブラリ:
  pip install google-genai sounddevice numpy
────────────────────────────────────────────────────────
"""

import asyncio
import sys
import os
from pathlib import Path

# ─────────────────────────────────────────────────────
# 設定読み込み
# ─────────────────────────────────────────────────────

def load_config() -> dict:
    """
    .env ファイルから設定を読み込む。
    GEMINI_KEY_1 / LIVE_MODEL / VOICE_NAME / SYSTEM_PROMPT に対応。
    """
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        print("[エラー] .env ファイルが見つかりません。")
        print("  .env.template をコピーして .env を作成し、APIキーを設定してください。")
        print(f"  場所: {env_path.parent}")
        sys.exit(1)

    cfg = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip().strip('"\'')

    # APIキー
    api_key = cfg.get("GEMINI_KEY_1", "")
    if not api_key or api_key.startswith("YOUR_"):
        print("[エラー] .env の GEMINI_KEY_1 にAPIキーが設定されていません。")
        print("  https://aistudio.google.com/apikey でキーを取得してください。")
        sys.exit(1)

    return {
        "api_key":       api_key,
        "model":         cfg.get("LIVE_MODEL",     "gemini-2.0-flash-live-001"),
        "voice_name":    cfg.get("VOICE_NAME",     "Kore"),
        "system_prompt": cfg.get("SYSTEM_PROMPT",  "あなたは日本語で話す親切なアシスタントです。"),
    }


# ─────────────────────────────────────────────────────
# テキストモード（デバッグ・音声デバイスなし環境用）
# ─────────────────────────────────────────────────────

async def run_text_mode(cfg: dict):
    """
    テキスト入出力でLive APIをテストするモード。
    音声デバイスが不要なので環境確認に使える。
    """
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=cfg["api_key"],
        http_options={"api_version": "v1beta"},
    )

    live_config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=cfg["system_prompt"],
    )

    print(f"  モデル : {cfg['model']}")
    print(f"  モード : テキスト")
    print("  接続中...")

    async with client.aio.live.connect(
        model=cfg["model"], config=live_config
    ) as session:
        print("  接続完了！\n")
        print("  メッセージを入力してください。exit で終了。\n")

        while True:
            try:
                user_input = input("あなた > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  終了します。")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("  終了します。")
                break

            # テキスト送信（end_of_turn=True で応答を要求）
            await session.send(input=user_input, end_of_turn=True)

            # 応答受信
            print("AI > ", end="", flush=True)
            async for response in session.receive():
                if response.text:
                    print(response.text, end="", flush=True)
                if response.server_content and response.server_content.turn_complete:
                    break
            print()  # 改行


# ─────────────────────────────────────────────────────
# 音声モード（メイン機能）
# ─────────────────────────────────────────────────────

async def run_voice_mode(cfg: dict):
    """
    マイク入力 → Live API → スピーカー出力のリアルタイム音声対話。
    """
    try:
        import sounddevice as sd
        import numpy as np
    except ImportError:
        print("[エラー] sounddevice / numpy が未インストールです。")
        print("  pip install sounddevice numpy を実行してください。")
        sys.exit(1)

    from google import genai
    from google.genai import types

    # ── 音声設定 ──────────────────────────────────────
    INPUT_RATE  = 16000   # マイク: Live APIの要件 (16kHz)
    OUTPUT_RATE = 24000   # スピーカー: Live APIの出力 (24kHz)
    CHUNK       = 1024    # 1チャンクあたりのサンプル数

    client = genai.Client(
        api_key=cfg["api_key"],
        http_options={"api_version": "v1beta"},
    )

    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=cfg["voice_name"]
                )
            )
        ),
        system_instruction=cfg["system_prompt"],
    )

    print(f"  モデル : {cfg['model']}")
    print(f"  声    : {cfg['voice_name']}")
    print(f"  モード : 音声")
    print("  接続中...")

    # ── asyncio ループ取得（sounddeviceコールバック用）──
    loop = asyncio.get_event_loop()

    # マイク音声をメインループのキューに転送するキュー
    mic_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def mic_callback(indata, frames, time_info, status):
        """sounddevice の入力コールバック（別スレッドで呼ばれる）"""
        loop.call_soon_threadsafe(mic_queue.put_nowait, bytes(indata))

    async with client.aio.live.connect(
        model=cfg["model"], config=live_config
    ) as session:
        print("  接続完了！")
        print("  話しかけてください。会話は自動で検出されます。")
        print("  Ctrl+C で終了\n")

        # ── 音声ストリームを開始 ──────────────────────
        input_stream = sd.RawInputStream(
            samplerate=INPUT_RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK,
            callback=mic_callback,
        )
        output_stream = sd.RawOutputStream(
            samplerate=OUTPUT_RATE,
            channels=1,
            dtype="int16",
        )

        input_stream.start()
        output_stream.start()

        # ── 送信タスク: マイク → Live API ────────────
        async def send_loop():
            while True:
                pcm = await mic_queue.get()
                await session.send(
                    input=types.Blob(data=pcm, mime_type="audio/pcm")
                )

        # ── 受信タスク: Live API → スピーカー ─────────
        async def receive_loop():
            async for response in session.receive():
                # 音声データをスピーカーへ
                if response.data:
                    output_stream.write(response.data)

                # テキスト字幕（AIが話している内容を表示）
                if response.text:
                    print(f"\r  [AI] {response.text}", end="", flush=True)

                # ターン終了で改行
                if (
                    response.server_content
                    and response.server_content.turn_complete
                ):
                    print()

        # ── 両タスクを並列実行 ────────────────────────
        try:
            await asyncio.gather(send_loop(), receive_loop())
        finally:
            input_stream.stop()
            input_stream.close()
            output_stream.stop()
            output_stream.close()


# ─────────────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────────────

def print_header():
    print()
    print("  ┌────────────────────────────────────────┐")
    print("  │   unilive — Gemini Live API 音声対話   │")
    print("  └────────────────────────────────────────┘")
    print()


def main():
    print_header()

    cfg = load_config()

    # --text フラグでテキストモードに切り替え
    text_mode = "--text" in sys.argv

    try:
        if text_mode:
            asyncio.run(run_text_mode(cfg))
        else:
            asyncio.run(run_voice_mode(cfg))
    except KeyboardInterrupt:
        print("\n  終了しました。")
    except Exception as e:
        print(f"\n  [エラー] {e}")
        print()
        print("  ヒント:")
        print("    音声デバイスのエラーの場合 → python voice_mode.py --text で動作確認")
        print("    APIキーのエラーの場合      → .env の GEMINI_KEY_1 を確認")
        raise


if __name__ == "__main__":
    main()
