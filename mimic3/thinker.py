"""
thinker.py — Mistral Large 3 Thinker
======================================
ツール呼び出しを一切行わず、詳細な実装仕様だけを生成する「テックリード」役。
Actor（OwlAlpha）へ渡す指示書の品質がシステム全体の品質を左右するため、
プロンプト設計・エラーハンドリングを丁寧に実装する。
"""
from __future__ import annotations

import json
import re
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


THINKER_STEP_REVIEW_PROMPT = """\
あなたは優秀なテックリードです。
実行者（Actor）が1ステップを完了しました。その結果を評価し、残りの計画を続行すべきか、修正すべきかを判断してください。

# 絶対ルール（違反すると処理が失敗する）
- **出力はJSONのみ**。前後・途中に一切のテキスト・説明・思考を含めてはならない
- **```json などのコードブロックで囲ってはならない**
- 出力の1文字目は必ず `{` でなければならない

# 出力形式（3パターンのどれか1つ）
{"action":"continue","reason":"判断理由を1文で"}
{"action":"replan","reason":"判断理由","steps":[{"label":"","description":"ステップの説明","on_failure":"retry","on_success":"","max_iterations":0}]}
{"action":"done","reason":"完了理由を1文で"}

# action の意味
- "continue": 残りのステップをそのまま続行する（期待通りの結果だった場合）
- "replan": 実行結果を踏まえ、残りのステップを差し替える（予期しない状況が発生した場合）
- "done": 全体ゴールが達成された。これ以上のステップは不要（タスク完了時のみ使う）

# replan 時の steps フィールドのルール
- 残りすべての作業を含めること（完了済みステップは不要）
- フォーマット: label/description/on_failure/on_success/max_iterations のみ使用
- 空配列は禁止（replan なら必ず1件以上）
- ファイルを編集するステップの直前には必ず「対象ファイルを全て読み取る」ステップを置く

# 判断基準
- ステップが正常に完了した → continue
- エラーが起きたが Actor が解決済み → continue
- 実行結果が次のステップの前提を変えた → replan
- 残りのステップがすでに不要になった、またはゴール達成 → done
"""


class MistralAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status  = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class MistralRateLimitError(MistralAPIError):
    pass


# ── 計画生成専用プロンプト ────────────────────────────────────────
THINKER_PLAN_PROMPT = """\
あなたは優秀なテックリードです。
ユーザーのタスクを具体的な実行ステップに分解し、JSONのみを出力してください。

# 実行者（Actor）について
- PowerShell コマンド実行（git・gh CLI・npm・node など）
- ファイルの読み取り・編集・作成・削除
- 作業ディレクトリ: Windows 環境
- ファイルを編集する前に必ず全て読み取ること

# 絶対ルール（違反すると処理が失敗する）
- **出力はJSONのみ**。前後・途中に一切のテキスト・説明・思考を含めてはならない
- **```json などのコードブロックで囲ってはならない**
- 出力の1文字目は必ず `{` でなければならない
- ファイル編集ステップの直前には必ず「対象ファイルを全て読み取る」ステップを置く

# 出力形式（このフィールドのみ使用すること）
{"steps":[
  {"label":"","description":"ステップの説明","parallel":false,"on_failure":"retry","on_success":"","max_iterations":0},
  {"label":"check","description":"確認ステップ","parallel":false,"on_failure":"goto:fallback","on_success":"","max_iterations":3},
  {"label":"fallback","description":"代替手段","parallel":false,"on_failure":"skip","on_success":"","max_iterations":0}
]}

# フィールドの説明
- label: goto のジャンプ先となる名前（省略可）
- description: ステップの説明（実行者への指示）
- parallel: false（現在は逐次実行のみ）
- on_failure: "retry"（デフォルト）| "skip" | "abort" | "goto:<label>"
- on_success: ""（デフォルト・次へ）| "goto:<label>" | "abort"
- max_iterations: goto ループの上限（0=安全上限10を自動適用）

# 絶対禁止フィールド
- "command" フィールドは含めてはならない（JSONを破壊する）
- "content" フィールドは含めてはならない（JSONを破壊する）
- "code" フィールドは含めてはならない
- 上記6フィールド以外は一切含めないこと
"""


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

    def plan(self, user_message: str) -> list[dict]:
        """
        ユーザータスクを WorkflowGraph 用の PlanStep リストに分解する。
        Mistral に JSON を生成させ、パースして返す。
        会話履歴に記録するので review() でこの計画を参照できる。
        """
        self.conversation.append({"role": "user", "content": user_message})

        # 計画生成時は THINKER_PLAN_PROMPT で上書き
        original_prompt = self.system_prompt
        self.system_prompt = THINKER_PLAN_PROMPT
        safe_print(C.gray(f"  → mistral ({self.config.model}) [plan]"), flush=True)

        # ストリーミングで JSON を受け取る（レンダリングは不要なのでシンプル表示）
        safe_print(C.bold_mem(f"  ╔{'═' * 54}"))
        safe_print(C.bold_mem(f"  ║  ✦ 計画生成 (Mistral)"))
        safe_print(C.mem(f"  ╟{'─' * 54}"))
        raw_json = self._stream_call_api(self.conversation)
        safe_print(f"\n{C.bold_mem(f'  ╚{chr(9552) * 54}')}\n")

        self.system_prompt = original_prompt  # プロンプトを元に戻す
        self.conversation.append({"role": "assistant", "content": raw_json})

        # JSON パース
        steps = self._parse_plan_json(raw_json)
        log.info({"event": "thinker_plan", "steps": len(steps)})
        return steps

    @staticmethod
    def _parse_plan_json(text: str) -> list[dict]:
        """
        JSON テキストから steps リストを抽出する。
        Mistral が ```json ... ``` で返す場合も対応。
        """
        # ── Step 1: ```json ... ``` コードブロックを剥がす ──────────
        stripped = text.strip()
        m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', stripped)
        if m:
            stripped = m.group(1).strip()

        # ── Step 1b: command/content フィールドを除去（JSONを壊す複雑な値）──
        # カンマ付き・なし両パターンで削除（DOTALL で複数行対応）
        for field in ("command", "content", "code"):
            stripped = re.sub(
                rf',?\s*"{field}"\s*:\s*"(?:[^"\\]|\\.)*"',
                '',
                stripped,
                flags=re.DOTALL,
            )

        # ── Step 2: brace-matching で最外の { ... } ブロックを探す ──
        def _iter_json_blocks(s: str):
            i = 0
            while i < len(s):
                if s[i] == '{':
                    depth, start = 0, i
                    for j in range(i, len(s)):
                        if s[j] == '{':
                            depth += 1
                        elif s[j] == '}':
                            depth -= 1
                            if depth == 0:
                                yield s[start:j + 1]
                                i = j
                                break
                i += 1

        for block in _iter_json_blocks(stripped):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            steps_raw = data.get("steps", [])
            if not steps_raw or not isinstance(steps_raw, list):
                continue
            result = []
            for s in steps_raw[:20]:
                if not isinstance(s, dict):
                    continue
                desc = str(s.get("description", "")).strip()
                if not desc:
                    continue
                result.append({
                    "description":    desc,
                    "parallel":       False,  # 安全のため常に逐次
                    "label":          str(s.get("label", "")),
                    "on_failure":     str(s.get("on_failure", "retry")),
                    "on_success":     str(s.get("on_success", "")),
                    "max_iterations": int(s.get("max_iterations", 0)),
                })
            if result:
                return result

        # ── Step 3: パース完全失敗 → 空リストを返す（呼び出し側でエラー表示）──
        log.warning({"event": "thinker_plan_parse_failed", "text_preview": text[:300]})
        return []

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

    def step_review(
        self,
        original_goal: str,
        just_executed: str,
        step_result: str,
        remaining_steps: list,
        executed_log: list,
    ) -> dict:
        """
        1ステップ実行後にその結果を評価し、残りの計画を続行・修正・完了を判断する。
        戻り値: {"action": "continue"|"replan"|"done", "reason": "...", "steps": [...]}
        """
        remaining_text = "\n".join(
            f"  {i+1}. {s.get('description', str(s))[:80]}"
            for i, s in enumerate(remaining_steps[:10])
        ) if remaining_steps else "（残りステップなし）"

        log_text = "\n".join(
            f"  ✓ {e['description'][:60]}"
            for e in executed_log[-3:]
        ) if executed_log else "（なし）"

        prompt = (
            f"[全体ゴール]\n{original_goal}\n\n"
            f"[完了済みステップ]\n{log_text}\n\n"
            f"[今実行したステップ]\n{just_executed}\n\n"
            f"[実行結果]\n{step_result[:1500]}\n\n"
            f"[残りのステップ]\n{remaining_text}\n\n"
            "上記を踏まえて action を決定し、JSONのみを出力してください。"
        )
        self.conversation.append({"role": "user", "content": prompt})

        original_prompt = self.system_prompt
        self.system_prompt = THINKER_STEP_REVIEW_PROMPT
        safe_print(C.gray(f"  → mistral ({self.config.model}) [step_review]"), flush=True)
        raw = self._stream_with_box("ステップ評価 (Mistral)", self.conversation)
        self.system_prompt = original_prompt

        self.conversation.append({"role": "assistant", "content": raw})
        log.info({"event": "thinker_step_review", "raw_length": len(raw)})

        return self._parse_step_decision(raw)

    @staticmethod
    def _parse_step_decision(text: str) -> dict:
        """
        step_review の JSON 出力をパースする。
        失敗時は安全側フォールバック {"action": "continue"} を返す。
        """
        stripped = text.strip()
        m = re.search(r'```(?:json)?\s*([\s\S]+?)\s*```', stripped)
        if m:
            stripped = m.group(1).strip()

        def _iter_json_blocks(s: str):
            i = 0
            while i < len(s):
                if s[i] == '{':
                    depth, start = 0, i
                    for j in range(i, len(s)):
                        if s[j] == '{':
                            depth += 1
                        elif s[j] == '}':
                            depth -= 1
                            if depth == 0:
                                yield s[start:j + 1]
                                i = j
                                break
                i += 1

        for block in _iter_json_blocks(stripped):
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                continue
            action = data.get("action", "")
            if action not in ("continue", "replan", "done"):
                continue
            result: dict = {"action": action, "reason": str(data.get("reason", ""))}
            if action == "replan":
                raw_steps = data.get("steps", [])
                parsed: list[dict] = []
                for s in raw_steps[:20]:
                    if not isinstance(s, dict):
                        continue
                    desc = str(s.get("description", "")).strip()
                    if not desc:
                        continue
                    parsed.append({
                        "description":    desc,
                        "parallel":       False,
                        "label":          str(s.get("label", "")),
                        "on_failure":     str(s.get("on_failure", "retry")),
                        "on_success":     str(s.get("on_success", "")),
                        "max_iterations": int(s.get("max_iterations", 0)),
                    })
                if not parsed:
                    log.warning({"event": "step_review_replan_empty_steps"})
                    return {"action": "continue", "reason": "replan steps が空のため continue にフォールバック"}
                result["steps"] = parsed
            return result

        log.warning({"event": "step_review_parse_failed", "text_preview": text[:200]})
        return {"action": "continue", "reason": "パース失敗 → 安全側 continue"}
