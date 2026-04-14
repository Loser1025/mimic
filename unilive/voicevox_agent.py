"""
voicevox_agent.py
────────────────────────────────────────────────────────────────
VOICEVOX + Gemini Flash + V4 フルスタック統合
低レイテンシ日本語音声エージェント

■ パイプライン（低レイテンシ設計）
    マイク
      ↓ エネルギーVAD（発話区間を自動検出）
    faster-whisper STT（ローカル、CPU int8）
      ↓
    Gemini Flash ストリーミング推論
      ↓ 文が完成した瞬間に TTS 開始
    VOICEVOX 音声合成（HTTP API）  ← 文 N+1 を先行合成
      ↓
    スピーカー出力（重畳再生）

■ レート制限回避
    V4.py の AccountRotator + TokenBucket を流用。
    .env の GEMINI_KEY_1〜9 を全て管理し、
    429/503 受信時に指数バックオフ + 別キーへ自動ローテーション。

■ 起動前の準備
    1. VOICEVOX を起動（http://127.0.0.1:50021）
    2. pip install faster-whisper
    3. .env に GEMINI_KEY_1〜N を設定

■ 起動方法
    python voicevox_agent.py                 # 音声モード
    python voicevox_agent.py --text          # テキストモード（STT不要）
    python voicevox_agent.py --speakers      # 話者一覧を表示
    python voicevox_agent.py --speaker 3     # 話者IDを指定（デフォルト: 3）
    python voicevox_agent.py --whisper base  # Whisperモデルを指定
"""

import sys
import re
import json
import time
import wave
import io
import queue
import random
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import requests

# ── パス設定 ──────────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

print("  V4 を読み込み中...", flush=True)
try:
    import V4 as _v4
except ImportError as e:
    print(f"[エラー] V4.py のインポートに失敗: {e}")
    sys.exit(1)

C          = _v4.C
safe_print = _v4.safe_print
_tools     = _v4.tools
_SKIP      = {"ask_user"}

# ── ターゲットモデル ──────────────────────────────────────────────
TARGET_MODEL   = "gemma-4-26b-a4b-it"
BASE_BACKOFF   = 5.0
MAX_RETRIES    = 12

# ════════════════════════════════════════════════════════════════
#  設定読み込み（V4 の load_config を使いキーを全取得）
# ════════════════════════════════════════════════════════════════

def load_vvx_config() -> dict:
    """
    V4.load_config() でアカウント一覧を取得しつつ、
    VoiceVOX 固有設定も .env から読み込む。
    """
    env_path = _HERE / ".env"
    if not env_path.exists():
        safe_print(C.red("  [エラー] .env が見つかりません。"))
        sys.exit(1)

    raw: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        raw[k.strip()] = v.strip().strip('"\'')

    # V4 の AccountRotator を構築（全キーを管理）
    accounts, _sys_prompt = _v4.load_config(str(_HERE))

    # モデルを TARGET_MODEL に強制上書き
    for acc in accounts:
        acc.model = TARGET_MODEL

    system_prompt = raw.get("SYSTEM_PROMPT",
        "あなたは日本語で話す高機能AIエージェントです。"
        "ユーザーの指示に従い、必要に応じてツールを使ってタスクを実行します。"
        "音声で応答するので、できるだけ簡潔に話してください。"
    )

    return {
        "accounts":      accounts,
        "rotator":       _v4.AccountRotator(accounts),
        "voicevox_url":  raw.get("VOICEVOX_URL",    "http://127.0.0.1:50021"),
        "speaker_id":    int(raw.get("VVX_SPEAKER",  "3")),
        "whisper_model": raw.get("WHISPER_MODEL",    "tiny"),
        "system_prompt": system_prompt,
        "cwd":           raw.get("WORK_DIR",          str(Path.cwd())),
    }


# ════════════════════════════════════════════════════════════════
#  Gemini API 呼び出し（ストリーミング + レートリミット回避）
# ════════════════════════════════════════════════════════════════

def _gemini_stream(rotator: "_v4.AccountRotator", contents: list,
                   tools_spec: list, system_instruction: str):
    """
    V4 の AccountRotator + TokenBucket を使い、
    429/503 を受けた場合は指数バックオフ＋別キーにローテーションして
    ストリーミングジェネレーターを返す。

    yield: チャンクオブジェクト（chunk.candidates[0].content.parts）
    """
    from google import genai
    from google.genai import types, errors as genai_errors

    for attempt in range(MAX_RETRIES):
        account, wait = rotator.pick()
        if wait > 0:
            safe_print(C.yellow(f"  ⏳ RPM 待機 {wait:.1f}s ({account.name})"), flush=True)
            time.sleep(wait)
            rotator.record(account)

        client = genai.Client(api_key=account.api_key)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools_spec,
            temperature=0.7,
        )

        try:
            stream = client.models.generate_content_stream(
                model=account.model,
                contents=contents,
                config=config,
            )
            # 正常時はジェネレーターをそのまま返す
            yield from stream
            return

        except genai_errors.APIError as e:
            code = getattr(e, "code", None) or getattr(e, "status_code", 0)
            status = getattr(e, "status", None) or str(code)

            if code == 429:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2), 90)
                safe_print(C.yellow(
                    f"  ⚠ 429 ({account.name}) → {backoff:.0f}s 待機してリトライ"
                ), flush=True)
                time.sleep(backoff)
                continue

            if str(status) in ("500", "503"):
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2), 60)
                safe_print(C.yellow(
                    f"  ⚠ サーバーエラー {status} → {backoff:.0f}s 待機"
                ), flush=True)
                time.sleep(backoff)
                continue

            raise  # その他は上位に投げる

        except Exception as e:
            backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2), 60)
            safe_print(C.yellow(
                f"  ⚠ 接続エラー ({type(e).__name__}) → {backoff:.0f}s 待機"
            ), flush=True)
            time.sleep(backoff)
            continue

    raise RuntimeError(f"Gemini API: {MAX_RETRIES} 回リトライしても失敗しました。")


# ════════════════════════════════════════════════════════════════
#  VOICEVOX クライアント
# ════════════════════════════════════════════════════════════════

class VoicevoxClient:
    def __init__(self, base_url: str, speaker_id: int):
        self.base_url   = base_url.rstrip("/")
        self.speaker_id = speaker_id
        self._sess      = requests.Session()

    def alive(self) -> bool:
        try:
            return self._sess.get(f"{self.base_url}/version", timeout=3).status_code == 200
        except Exception:
            return False

    def speakers(self) -> list:
        r = self._sess.get(f"{self.base_url}/speakers", timeout=5)
        r.raise_for_status()
        return r.json()

    def synthesize(self, text: str) -> bytes:
        """テキスト → WAV bytes"""
        r = self._sess.post(
            f"{self.base_url}/audio_query",
            params={"text": text, "speaker": self.speaker_id},
            timeout=10,
        )
        r.raise_for_status()
        r2 = self._sess.post(
            f"{self.base_url}/synthesis",
            params={"speaker": self.speaker_id},
            json=r.json(),
            timeout=30,
        )
        r2.raise_for_status()
        return r2.content


# ════════════════════════════════════════════════════════════════
#  TtsPipeline — 合成→再生を順序保証で直列処理
# ════════════════════════════════════════════════════════════════

class TtsPipeline:
    """
    合成スレッド → 再生スレッドの2段キューパイプライン。
    文の順序を保ちつつ、合成と再生を重畳して低レイテンシを実現。
    wait_done() は合成・再生が全て完了するまで確実にブロックする。
    """

    def __init__(self, vvx: VoicevoxClient):
        self._vvx     = vvx
        self._synth_q: queue.Queue = queue.Queue()  # str  → 合成スレッドへ
        self._play_q:  queue.Queue = queue.Queue()  # bytes → 再生スレッドへ

        threading.Thread(target=self._synth_loop, daemon=True).start()
        threading.Thread(target=self._play_loop,  daemon=True).start()

    def push(self, text: str):
        """文を合成キューに追加（ノンブロッキング）"""
        if text.strip():
            self._synth_q.put(text)

    def wait_done(self):
        """合成・再生が全て完了するまで待機"""
        self._synth_q.join()
        self._play_q.join()

    def _synth_loop(self):
        while True:
            text = self._synth_q.get()
            try:
                wav = self._vvx.synthesize(text)
                self._play_q.put(wav)
            except Exception as e:
                safe_print(C.yellow(f"  [TTS] 合成失敗: {e}"), flush=True)
            finally:
                self._synth_q.task_done()

    def _play_loop(self):
        while True:
            wav = self._play_q.get()
            try:
                self._play_wav(wav)
            except Exception as e:
                safe_print(C.yellow(f"  [再生] エラー: {e}"), flush=True)
            finally:
                self._play_q.task_done()

    @staticmethod
    def _play_wav(wav_bytes: bytes):
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            rate   = wf.getframerate()
            swidth = wf.getsampwidth()
            nch    = wf.getnchannels()
            data   = np.frombuffer(wf.readframes(wf.getnframes()),
                                   dtype={1: np.int8, 2: np.int16, 4: np.int32}[swidth])
        if nch > 1:
            data = data.reshape(-1, nch)
        # sd.play()+sd.wait() はスレッド内で不安定なため OutputStream で直接書き込む
        channels = data.shape[1] if data.ndim > 1 else 1
        with sd.OutputStream(samplerate=rate, channels=channels, dtype=data.dtype) as stream:
            stream.write(data)


# ════════════════════════════════════════════════════════════════
#  SentenceBuffer — ストリームを文単位に分割して TTS へ渡す
# ════════════════════════════════════════════════════════════════

# 日本語文区切り（読点含む長い文も対象）
_SENT_RE = re.compile(r'[^。！？!?\n]{2,}[。！？!?\n]')

class SentenceBuffer:
    """
    ストリームで届くテキストを貯め、文が完成した瞬間に callback(sentence) を呼ぶ。
    flush() で残りのバッファを強制送出。
    """
    def __init__(self, callback):
        self._buf = ""
        self._cb  = callback

    def push(self, text: str):
        self._buf += text
        while True:
            m = _SENT_RE.search(self._buf)
            if not m:
                break
            sentence = m.group().strip()
            self._buf = self._buf[m.end():]
            if sentence:
                self._cb(sentence)

    def flush(self):
        tail = self._buf.strip()
        self._buf = ""
        if tail:
            self._cb(tail)


# ════════════════════════════════════════════════════════════════
#  WhisperSTT — faster-whisper によるローカル音声認識
# ════════════════════════════════════════════════════════════════

class WhisperSTT:
    def __init__(self, model_size: str = "tiny"):
        safe_print(C.gray(f"  Whisper ({model_size}) を読み込み中..."), flush=True)
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(model_size, device="cpu", compute_type="int8")
            safe_print(C.green("  Whisper 準備完了"), flush=True)
        except ImportError:
            safe_print(C.red(
                "  [エラー] faster-whisper が未インストールです。\n"
                "  pip install faster-whisper を実行してください。"
            ), flush=True)
            sys.exit(1)

    def transcribe(self, audio: np.ndarray, sr: int = 16000) -> str:
        a = audio.astype(np.float32)
        if a.max() > 1.0:
            a /= 32768.0
        segs, _ = self._model.transcribe(
            a, language="ja", beam_size=1, best_of=1, temperature=0.0,
            vad_filter=True,
        )
        return "".join(s.text for s in segs).strip()


# ════════════════════════════════════════════════════════════════
#  VoiceRecorder — エネルギーVAD で発話区間を録音
# ════════════════════════════════════════════════════════════════

class VoiceRecorder:
    SR          = 16000
    CHUNK       = 512
    THRESH      = 350       # RMS 閾値（環境に応じて調整）
    SILENCE_SEC = 1.2       # 無音判定秒
    MIN_MS      = 400       # 最低発話長(ms)

    def record(self) -> Optional[np.ndarray]:
        silence_chunks = int(self.SILENCE_SEC * self.SR / self.CHUNK)
        frames: list[np.ndarray] = []
        silent = 0
        recording = False

        safe_print(C.gray("  🎙  話しかけてください..."), flush=True)
        with sd.InputStream(samplerate=self.SR, channels=1, dtype="int16",
                            blocksize=self.CHUNK) as stream:
            try:
                while True:
                    chunk, _ = stream.read(self.CHUNK)
                    rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                    if rms > self.THRESH:
                        if not recording:
                            recording = True
                            safe_print(C.cyan("  ◉ 録音中..."), flush=True)
                        silent = 0
                        frames.append(chunk.copy())
                    elif recording:
                        frames.append(chunk.copy())
                        silent += 1
                        if silent >= silence_chunks:
                            break
            except KeyboardInterrupt:
                return None

        if not frames:
            return None
        audio = np.concatenate(frames).flatten()
        if len(audio) / self.SR * 1000 < self.MIN_MS:
            return None
        return audio


# ════════════════════════════════════════════════════════════════
#  ツール定義構築
# ════════════════════════════════════════════════════════════════

def build_tools_spec() -> list:
    from google.genai import types
    decls = []
    for spec in _tools.get_specs():
        if spec["name"] in _SKIP:
            continue
        try:
            decls.append(types.FunctionDeclaration(
                name=spec["name"],
                description=spec["description"],
                parameters=spec.get("parameters", {"type": "object", "properties": {}}),
            ))
        except Exception as e:
            safe_print(C.yellow(f"  [警告] ツール '{spec['name']}' 変換失敗: {e}"), flush=True)
    safe_print(C.gray(f"  ツール登録: {len(decls)} 件"), flush=True)
    from google.genai import types as t
    return [t.Tool(function_declarations=decls)]


# ════════════════════════════════════════════════════════════════
#  メインエージェント
# ════════════════════════════════════════════════════════════════

class VoicevoxAgent:
    """
    VOICEVOX + Gemini Flash + V4ToolExecutor

    低レイテンシ TTS パイプライン:
      文が完成した瞬間に VOICEVOX 合成を開始し、
      再生キューに追加（合成と再生を並走させる）。
    """

    def __init__(self, cfg: dict):
        self.cfg     = cfg
        self.rotator: "_v4.AccountRotator" = cfg["rotator"]
        self.cwd     = cfg["cwd"]
        self.vvx     = VoicevoxClient(cfg["voicevox_url"], cfg["speaker_id"])
        self.tts     = TtsPipeline(self.vvx)
        self.tools_spec = build_tools_spec()

        # V4 コンポーネント
        ltm = _v4.LongTermMemory(str(_HERE / "lessons_db.json"))
        from voice_agent import V4ToolExecutor
        self.executor = V4ToolExecutor(self.cwd, cfg["accounts"][0].api_key, ltm)

        # 会話履歴
        self.history: list = []

    # ── システムプロンプト ─────────────────────────────────────────

    @property
    def _sys_prompt(self) -> str:
        return (
            f"{self.cfg['system_prompt']}\n\n"
            f"## 作業フォルダ\n  {self.cwd}\n\n"
            "## 作業ルール\n"
            "- 音声応答なので簡潔に話してください\n"
            "- ツール実行前に何をするか一言説明してください\n"
            "- 複数の独立した読み取りは並列で行ってください\n"
            "- 依頼されていない改善を自発的に行わないでください\n"
        )

    # ── TTS ──────────────────────────────────────────────────────

    def _speak(self, text: str):
        """TtsPipeline に文を追加（合成→再生は順序保証）"""
        self.tts.push(text)

    # ── 1ターン処理 ────────────────────────────────────────────────

    def _run_turn(self, user_text: str) -> str:
        """
        1. Gemini Flash にストリーミング問い合わせ
        2. 文が完成した瞬間に VOICEVOX TTS 開始（低レイテンシ）
        3. ツール呼び出しがあれば V4ToolExecutor で実行
        4. 最終テキストを返す
        """
        from google.genai import types

        self.history.append(types.Content(
            role="user",
            parts=[types.Part(text=f"[作業フォルダ] {self.cwd}\n\n{user_text}")]
        ))

        full_response_parts: list[str] = []

        while True:
            sent_buf = SentenceBuffer(self._speak)
            text_parts: list[str] = []
            tool_calls: list      = []

            safe_print(C.bold_purple("\nAI > "), end="", flush=True)

            try:
                for chunk in _gemini_stream(
                    self.rotator, self.history, self.tools_spec, self._sys_prompt
                ):
                    if not chunk.candidates:
                        continue
                    cand = chunk.candidates[0]
                    if not cand.content or not cand.content.parts:
                        continue

                    for part in cand.content.parts:
                        if hasattr(part, "text") and part.text:
                            safe_print(part.text, end="", flush=True)
                            text_parts.append(part.text)
                            sent_buf.push(part.text)

                        if hasattr(part, "function_call") and part.function_call:
                            tool_calls.append(part.function_call)

            except Exception as e:
                safe_print(C.red(f"\n  [Gemini] エラー: {e}"), flush=True)
                break

            safe_print(flush=True)

            # テキストを履歴に追加
            if text_parts:
                sent_buf.flush()  # 残りを TTS に流す
                joined = "".join(text_parts)
                full_response_parts.append(joined)
                self.history.append(types.Content(
                    role="model",
                    parts=[types.Part(text=joined)]
                ))

            # ツール呼び出しがなければ終了
            if not tool_calls:
                break

            # ── ツール実行 ─────────────────────────────────────────
            self._speak("ツールを実行します。")

            self.history.append(types.Content(
                role="model",
                parts=[types.Part(function_call=fc) for fc in tool_calls]
            ))

            calls = [{"name": fc.name, "args": dict(fc.args or {})} for fc in tool_calls]
            results = self.executor.execute_batch(calls)

            result_parts = []
            for (fn_name, result), fc in zip(results, tool_calls):
                result_parts.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=fn_name,
                        response={"output": result}
                    )
                ))
            self.history.append(types.Content(role="user", parts=result_parts))

        # 再生完了を待つ
        self.tts.wait_done()
        return "\n".join(full_response_parts)

    # ── 音声モード ────────────────────────────────────────────────

    def run_voice(self, whisper_model: str):
        stt      = WhisperSTT(whisper_model)
        recorder = VoiceRecorder()

        safe_print(C.bold_green("\n  ◈ VOICEVOX 音声エージェント 起動"), flush=True)
        safe_print(C.green(f"  モデル    : {TARGET_MODEL}"), flush=True)
        safe_print(C.green(f"  キー数    : {len(self.cfg['accounts'])} 本"), flush=True)
        safe_print(C.green(f"  話者 ID   : {self.cfg['speaker_id']}"), flush=True)
        safe_print(C.green(f"  作業フォルダ: {self.cwd}"), flush=True)
        safe_print(C.gray("  「終了」と言うか Ctrl+C で終了\n"), flush=True)

        self._speak("起動しました。何でもどうぞ。")
        self.tts.wait_done()  # 挨拶を最後まで再生してから次へ
        self.executor.backup()

        while True:
            try:
                audio = recorder.record()
            except KeyboardInterrupt:
                break
            if audio is None:
                continue

            safe_print(C.gray("  文字起こし中..."), flush=True)
            t0 = time.time()
            text = stt.transcribe(audio)
            elapsed = time.time() - t0
            safe_print(C.cyan(f"\n  [あなた] {text}  ({elapsed:.1f}s)"), flush=True)

            if not text.strip():
                safe_print(C.gray("  （聞き取れませんでした）"), flush=True)
                continue

            if any(w in text for w in ["終了", "終わり", "バイバイ", "さようなら"]):
                self._speak("終了します。")
                self.tts.wait_done()
                break

            try:
                final = self._run_turn(text)
                if final:
                    self.executor.post_task(text, final, [])
            except KeyboardInterrupt:
                break
            except Exception as e:
                safe_print(C.red(f"\n  [エラー] {e}"), flush=True)

        safe_print(C.gray("  終了しました。"), flush=True)

    # ── テキストモード ────────────────────────────────────────────

    def run_text(self):
        safe_print(C.bold_green("\n  ◈ VOICEVOX テキストエージェント 起動"), flush=True)
        safe_print(C.green(f"  モデル    : {TARGET_MODEL}"), flush=True)
        safe_print(C.green(f"  キー数    : {len(self.cfg['accounts'])} 本"), flush=True)
        safe_print(C.green(f"  話者 ID   : {self.cfg['speaker_id']}"), flush=True)
        safe_print(C.gray("  /log, /undo, exit で操作\n"), flush=True)

        self._speak("起動しました。何でもどうぞ。")
        self.tts.wait_done()  # 挨拶を最後まで再生してから次へ
        self.executor.backup()

        while True:
            try:
                raw = input(C.bold_green("あなた > ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not raw:
                continue
            if raw.lower() in ("exit", "quit", "q"):
                break
            if raw == "/log":
                self.executor.react_log.display()
                continue
            if raw == "/undo":
                safe_print(C.yellow(f"  {self.executor.rollback()}"), flush=True)
                continue
            if raw == "/diff":
                safe_print(self.executor.diff(), flush=True)
                continue

            try:
                final = self._run_turn(raw)
                if final:
                    self.executor.post_task(raw, final, [])
            except Exception as e:
                safe_print(C.red(f"\n  [エラー] {e}"), flush=True)

        safe_print(C.gray("  終了しました。"), flush=True)


# ════════════════════════════════════════════════════════════════
#  エントリーポイント
# ════════════════════════════════════════════════════════════════

def _show_speakers(url: str):
    c = VoicevoxClient(url, 0)
    try:
        safe_print(C.bold_green("  VOICEVOX 話者一覧:"), flush=True)
        for sp in c.speakers():
            for style in sp.get("styles", []):
                safe_print(
                    C.gray(f"    ID {style['id']:4d}  ")
                    + C.cyan(f"{sp['name']}")
                    + C.gray(f"  /  {style['name']}"),
                    flush=True
                )
    except Exception as e:
        safe_print(C.red(f"  [エラー] VOICEVOX に接続できません: {e}"), flush=True)


def main():
    args = sys.argv[1:]

    cfg = load_vvx_config()

    # コマンドライン引数で上書き
    if "--speaker" in args:
        cfg["speaker_id"] = int(args[args.index("--speaker") + 1])
    if "--whisper" in args:
        cfg["whisper_model"] = args[args.index("--whisper") + 1]

    # 話者一覧
    if "--speakers" in args:
        _show_speakers(cfg["voicevox_url"])
        return

    # VOICEVOX 接続確認
    vvx = VoicevoxClient(cfg["voicevox_url"], cfg["speaker_id"])
    if not vvx.alive():
        safe_print(C.red(
            f"  [エラー] VOICEVOX に接続できません ({cfg['voicevox_url']})\n"
            "  VOICEVOX を起動してから再実行してください。"
        ), flush=True)
        sys.exit(1)
    safe_print(C.green(f"  VOICEVOX 接続OK  ({cfg['voicevox_url']})"), flush=True)

    agent = VoicevoxAgent(cfg)

    if "--text" in args:
        agent.run_text()
    else:
        agent.run_voice(cfg["whisper_model"])


if __name__ == "__main__":
    main()
