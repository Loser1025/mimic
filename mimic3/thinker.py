"""
thinker.py — Mistral Large 3 Thinker
======================================
ツール呼び出しを一切行わず、詳細な実装仕様だけを生成する「テックリード」役。
Actor（OwlAlpha）へ渡す指示書の品質がシステム全体の品質を左右するため、
プロンプト設計・エラーハンドリングを丁寧に実装する。
"""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Optional

from .config import MistralConfig, MISTRAL_API_BASE
from .utils import safe_print, C, log, PipelineTypewriter, render_markdown_thinker

# ── 定数 ────────────────────────────────────────────────────────
MAX_RETRIES = 4
BASE_BACKOFF = 2.0
MAX_BACKOFF  = 30.0

# Thinker が出力に含めると Actor へのループ終了を通知するマーカー
TASK_COMPLETE_MARKER = "[[TASK_COMPLETE]]"

# ── システムプロンプト ────────────────────────────────────────────
THINKER_SYSTEM_PROMPT = """\
あなたは優秀なテックリードです。
実装者（Actor）への詳細な指示書を生成することがあなたの唯一の仕事です。

# Actorについて
Actorは以下のツールを持つAIエージェントです：
- PowerShell コマンドの実行（ファイル操作・git・gh CLI・npm・node など）
- ファイルの読み取り・編集・作成・削除
- Web検索・Wikipedia参照
- 作業ディレクトリ: Windows環境

ActorはWebブラウザやUIを持ちません。コマンドラインとファイル操作で完結する指示を出してください。

# 絶対ルール
- ツール呼び出しは絶対に行わない。指示書テキストのみを出力する。
- 指示書は具体的・完全であること。コマンド例・ファイルパス・コードを含めること。
- Actorは文脈を持たない。必要な情報をすべて指示書に含めること。
- [[TASK_COMPLETE]] は必ずActorの報告を受けた後にのみ使う。
  初回（まだActorが何も実行していない状態）では絶対に使ってはならない。

# ファイル操作に関するルール（最重要）
- ファイルを編集・修正する指示を出す場合は、必ず最初に対象ファイルを
  **全て読み取ること（read_file で offset=0 から末尾まで）** を手順の
  最初のステップとして明記すること。
- 「ファイルの該当箇所を修正」などの曖昧な指示は禁止。
  読み取り完了後に編集するよう順序を明確に指定すること。
- 大きなファイルは offset を使って分割読み取りが必要な場合があることを
  指示書に含めること。

# 指示書のフォーマット
## 目的
（何を達成するか）

## 実行手順
（番号付きの具体的なステップ。実行するコマンドやコードを明記する）

## 完了条件
（何をもって完了とみなすか）

# タスク完了宣言（Actorの報告を受けた後のみ使用）
（最終確認・まとめ）

[[TASK_COMPLETE]]
"""


class MistralAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status  = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class MistralRateLimitError(MistralAPIError):
    pass


class MistralThinker:
    """
    Mistral Large 3 を使った Thinker。
    - ツール定義を持たない（ツール呼び出し不可）
    - Actor の実行サマリーを受け取り、次の詳細指示書を生成する
    - TASK_COMPLETE_MARKER を返したらタスク完了
    """

    def __init__(self, config: MistralConfig, base_system_prompt: str = ""):
        self.config        = config
        self.conversation: list[dict] = []
        # ベースプロンプト（.env の SYSTEM_PROMPT）をThinkerプロンプトに結合
        combined = base_system_prompt.strip()
        self.system_prompt = (
            f"{combined}\n\n{THINKER_SYSTEM_PROMPT}" if combined
            else THINKER_SYSTEM_PROMPT
        )

    def clear_history(self):
        self.conversation = []

    def _call_api(self, messages: list[dict]) -> str:
        """Mistral API を呼び出してテキストを返す。リトライ付き。"""
        # RPM 待機
        wait = self.config.acquire()
        if wait > 0:
            jitter = random.uniform(0.05, 0.3)
            safe_print(C.yellow(f"  ⏳ Thinker RPM待機 {wait + jitter:.1f}秒"), flush=True)
            time.sleep(wait + jitter)

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *messages,
            ],
            # ツール定義は渡さない（Thinker はツールを使えない）
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req  = urllib.request.Request(
            f"{MISTRAL_API_BASE}/chat/completions",
            data=body,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )

        attempt = 0
        while attempt < MAX_RETRIES:
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data["choices"][0]["message"]["content"] or ""

            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                try:
                    msg = json.loads(body_text).get("message", body_text)
                except Exception:
                    msg = body_text
                if e.code == 429:
                    backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF)
                    safe_print(C.yellow(f"  ⚠ Thinker 429 → {backoff:.0f}秒待機"), flush=True)
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise MistralAPIError(e.code, msg)

            except urllib.error.URLError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                safe_print(C.yellow(f"  ⚠ Thinker 接続エラー → {backoff:.0f}秒待機"), flush=True)
                time.sleep(backoff)
                attempt += 1

        raise MistralAPIError(0, f"Mistral API 最大リトライ({MAX_RETRIES})超過")

    def _stream_call_api(self, messages: list[dict], text_callback=None) -> str:
        """
        Mistral API をストリーミングで呼び出す。
        text_callback が渡された場合は各チャンクをコールバックに渡す（PipelineTypewriter 用）。
        渡されない場合は mem 色でそのまま出力する。
        """
        wait = self.config.acquire()
        if wait > 0:
            jitter = random.uniform(0.05, 0.3)
            safe_print(C.yellow(f"  ⏳ Thinker RPM待機 {wait + jitter:.1f}秒"), flush=True)
            time.sleep(wait + jitter)

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                *messages,
            ],
            "stream": True,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req  = urllib.request.Request(
            f"{MISTRAL_API_BASE}/chat/completions",
            data=body,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )

        attempt = 0
        while attempt < MAX_RETRIES:
            try:
                full_text = ""
                with urllib.request.urlopen(req, timeout=120) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8").rstrip("\n\r")
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:]
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        text_chunk = delta.get("content") or ""
                        if text_chunk:
                            if text_callback is not None:
                                text_callback(text_chunk)
                            else:
                                safe_print(C.mem(text_chunk), end="", flush=True)
                            full_text += text_chunk
                return full_text

            except urllib.error.HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                try:
                    msg = json.loads(body_text).get("message", body_text)
                except Exception:
                    msg = body_text
                if e.code == 429:
                    backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF)
                    safe_print(C.yellow(f"\n  ⚠ Thinker 429 → {backoff:.0f}秒待機"), flush=True)
                    time.sleep(backoff)
                    attempt += 1
                    continue
                raise MistralAPIError(e.code, msg)

            except urllib.error.URLError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                safe_print(C.yellow(f"\n  ⚠ Thinker 接続エラー → {backoff:.0f}秒待機"), flush=True)
                time.sleep(backoff)
                attempt += 1

        raise MistralAPIError(0, f"Mistral API ストリーミング最大リトライ({MAX_RETRIES})超過")

    def _stream_with_box(self, label: str, messages: list[dict]) -> str:
        """ボックスヘッダー表示 → PipelineTypewriter でストリーミング+レンダリング → フッター表示。"""
        safe_print(C.bold_mem(f"  ╔{'═' * 54}"))
        safe_print(C.bold_mem(f"  ║  ✦ {label}"))
        safe_print(C.mem(f"  ╟{'─' * 54}"))

        tw = PipelineTypewriter(renderer=render_markdown_thinker)
        tw.start()
        full_text = self._stream_call_api(messages, text_callback=tw.feed)
        tw.finalize()  # レンダリングスレッドの完了を待つ（Actor と完全独立）

        safe_print(C.bold_mem(f"  ╚{'═' * 54}\n"))
        return full_text

    def think(self, user_message: str) -> str:
        """指示書を生成する。ストリーミング+レンダリング表示しながら全文を返す。"""
        self.conversation.append({"role": "user", "content": user_message})

        safe_print(C.gray(f"  → mistral ({self.config.model}) [spec]"), flush=True)
        spec = self._stream_with_box("指示書 (Mistral)", self.conversation)
        self.conversation.append({"role": "assistant", "content": spec})

        log.info({"event": "thinker_spec", "length": len(spec)})
        return spec

    def review(self, actor_summary: str) -> str:
        """Actor の結果をレビューする。ストリーミング+レンダリング表示しながら全文を返す。"""
        review_prompt = (
            f"[Actorの実行結果]\n{actor_summary}\n\n"
            "上記の結果を踏まえて、以下の点を日本語で簡潔に報告してください：\n"
            "1. 完了したこと\n"
            "2. 残っている課題・懸念点（あれば）\n"
            "3. ユーザーへの推奨アクション\n\n"
            "次の指示書は不要です。レビューコメントのみ出力してください。"
        )
        self.conversation.append({"role": "user", "content": review_prompt})

        safe_print(C.gray(f"  → mistral ({self.config.model}) [review]"), flush=True)
        assessment = self._stream_with_box("レビュー (Mistral)", self.conversation)
        self.conversation.append({"role": "assistant", "content": assessment})

        log.info({"event": "thinker_review", "length": len(assessment)})
        return assessment
