from __future__ import annotations

import http.client
import json
import random
import re
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Any
from uuid import uuid4

from .utils import safe_print, C, log, cache_tool_output
from .config import OpenRouterConfig, OPENROUTER_API_BASE

MAX_RETRIES = 5
BASE_BACKOFF = 2.0
MAX_BACKOFF = 60.0
MAX_TOOL_ROUNDS = 60
_CACHEABLE_TOOLS = ["read_file", "list_directory", "search_files", "get_repo_map"]


# ── エラー定義 ────────────────────────────────────────────────────

class OpenRouterAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")


class RateLimitError(OpenRouterAPIError):
    pass


class ServerError(OpenRouterAPIError):
    pass



# ── AccountRotator 互換ラッパー ───────────────────────────────────

class AccountRotator:
    """OpenRouterConfig をラップし V4 の AccountRotator インタフェースを提供する。"""

    def __init__(self, config_or_list):
        if isinstance(config_or_list, OpenRouterConfig):
            self._config = config_or_list
        else:
            # OpenRouterConfig のリストが渡された場合
            from .config import OpenRouterConfig as _C
            api_keys = [getattr(a, "api_key", str(a)) for a in config_or_list]
            self._config = _C(api_keys=api_keys)

    def pick(self) -> tuple[OpenRouterConfig, float]:
        return self._config, 0.0

    def record(self, account):
        pass

    def can_afford_reviewer(self) -> bool:
        return True

    def wait_to_start(self, step_count: int) -> float:
        return 0.0

    def status(self) -> list[dict]:
        return [{"name": "openrouter", "keys": len(self._config.api_keys)}]

    @property
    def accounts(self) -> list[OpenRouterConfig]:
        return [self._config]

    @property
    def total_tokens(self) -> float:
        return 999.0


def _msg_char_count(m: dict) -> int:
    count = len(str(m.get("content", "") or ""))
    for tc in m.get("tool_calls", []):
        count += len(str(tc.get("function", {}).get("arguments", "")))
    return count


def _trim_messages_smart(messages: list[dict]) -> list[dict]:
    protected = messages[:2]
    body = messages[2:]
    if not body:
        return messages
    target_remove = max(2, len(body) // 4)
    # role=="tool" のメッセージを削除候補とする（OpenAI ネイティブ形式）
    tool_indices = [i for i, m in enumerate(body) if m.get("role") == "tool"]
    removed = 0
    indices_to_remove: set[int] = set()
    for idx in tool_indices:
        if removed >= target_remove:
            break
        indices_to_remove.add(idx)
        removed += 1
        # 直前の assistant+tool_calls メッセージも一緒に削除（孤立防止）
        if idx > 0 and body[idx - 1].get("tool_calls") and idx - 1 not in indices_to_remove:
            indices_to_remove.add(idx - 1)
    if removed < target_remove:
        for i in range(len(body)):
            if removed >= target_remove:
                break
            if i not in indices_to_remove:
                indices_to_remove.add(i)
                removed += 1
    return protected + [m for i, m in enumerate(body) if i not in indices_to_remove]


def _repair_message_sequence(messages: list[dict]) -> list[dict]:
    """孤立した tool_calls / tool ロールメッセージを除去する（OpenAI ネイティブ形式）。"""
    repaired = []
    i = 0
    while i < len(messages):
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            # 後続の tool メッセージを収集
            j = i + 1
            tool_msgs = []
            while j < len(messages) and messages[j].get("role") == "tool":
                tool_msgs.append(messages[j])
                j += 1
            expected_ids = {tc["id"] for tc in m["tool_calls"] if tc.get("id")}
            found_ids = {tm.get("tool_call_id") for tm in tool_msgs}
            if expected_ids and not expected_ids.issubset(found_ids):
                # 対応する tool 応答が揃っていない → ブロックごとスキップ
                log.warning({"event": "orphan_tool_calls_removed", "index": i})
                i = j
                continue
            repaired.append(m)
            repaired.extend(tool_msgs)
            i = j
        elif m.get("role") == "tool":
            # 直前が tool_calls を持つ assistant でなければ孤立
            prev = repaired[-1] if repaired else None
            if prev and prev.get("role") == "assistant" and prev.get("tool_calls"):
                repaired.append(m)
            else:
                log.warning({"event": "orphan_tool_result_removed", "index": i})
            i += 1
        else:
            repaired.append(m)
            i += 1
    return repaired


# ── API 呼び出し ──────────────────────────────────────────────────

def _acquire_key_with_wait(config: OpenRouterConfig) -> str:
    """RPM トークンが取れるまで待機し、使用する API キーを返す。"""
    while True:
        api_key, wait = config.acquire_key()
        if wait == 0.0:
            return api_key
        jitter = random.uniform(0.05, 0.3)
        actual_wait = wait + jitter
        safe_print(C.yellow(f"  ⏳ RPM待機中 {actual_wait:.1f}秒 (残トークン不足)"), flush=True)
        time.sleep(actual_wait)


def _build_openrouter_payload(
    config: OpenRouterConfig,
    messages: list[dict],
    tool_specs: list[dict],
    system_prompt: Optional[str],
    json_mode: bool,
) -> tuple[dict, str]:
    """ペイロードと使用する API キーを返す。変換不要・全てネイティブ OpenAI 形式。"""
    send_messages = []
    if system_prompt:
        send_messages.append({"role": "system", "content": system_prompt})
    send_messages.extend(messages)

    payload: dict[str, Any] = {
        "model": config.model,
        "messages": send_messages,
    }

    if tool_specs:
        payload["tools"] = tool_specs  # 既に OpenAI 形式
        payload["tool_choice"] = "auto"

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    api_key = _acquire_key_with_wait(config)
    return payload, api_key


def _call_openrouter_api(
    config: OpenRouterConfig,
    messages: list[dict],
    tool_specs: list[dict],
    system_prompt: Optional[str] = None,
    json_mode: bool = False,
) -> dict:
    payload, api_key = _build_openrouter_payload(config, messages, tool_specs, system_prompt, json_mode)
    url = f"{OPENROUTER_API_BASE}/chat/completions"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": config.site_url,
            "X-Title": config.site_name,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(body_text).get("error", {}).get("message", body_text)
        except Exception:
            msg = body_text
        if e.code == 429:
            raise RateLimitError(e.code, msg)
        if e.code >= 500:
            raise ServerError(e.code, msg)
        raise OpenRouterAPIError(e.code, msg)
    except urllib.error.URLError as e:
        raise OpenRouterAPIError(0, f"ネットワークエラー: {e.reason}")


def _stream_openrouter_api(
    config: OpenRouterConfig,
    messages: list[dict],
    tool_specs: list[dict],
    system_prompt: Optional[str] = None,
    json_mode: bool = False,
):
    """
    ストリーミング呼び出し。
    yields (text_chunk: str, tool_calls: list[dict], finish_reason: str)
    """
    payload, api_key = _build_openrouter_payload(config, messages, tool_specs, system_prompt, json_mode)
    payload["stream"] = True

    url = f"{OPENROUTER_API_BASE}/chat/completions"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": config.site_url,
            "X-Title": config.site_name,
        },
        method="POST",
    )

    # tool_calls はインデックスで蓄積する
    accumulated_tools: dict[int, dict] = {}

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").rstrip("\n\r")
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if not data_str or data_str == "[DONE]":
                    # 蓄積したツール呼び出しを最終チャンクで flush
                    if accumulated_tools:
                        chunk_tools = []
                        for idx in sorted(accumulated_tools):
                            t = accumulated_tools[idx]
                            try:
                                args = json.loads(t.get("arguments", "{}") or "{}")
                            except Exception:
                                args = {}
                            chunk_tools.append({"name": t.get("name", ""), "args": args, "id": t.get("id", "")})
                        yield "", chunk_tools, "tool_calls"
                    continue
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta", {})
                finish_reason = choice.get("finish_reason") or ""

                text_chunk = delta.get("content") or ""

                # tool_calls デルタの蓄積
                for tc_delta in (delta.get("tool_calls") or []):
                    idx = tc_delta.get("index", 0)
                    if idx not in accumulated_tools:
                        accumulated_tools[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.get("id"):
                        accumulated_tools[idx]["id"] = tc_delta["id"]
                    fn = tc_delta.get("function") or {}
                    if fn.get("name"):
                        accumulated_tools[idx]["name"] = fn["name"]
                    if fn.get("arguments"):
                        accumulated_tools[idx]["arguments"] += fn["arguments"]

                if finish_reason:
                    chunk_tools = []
                    for i in sorted(accumulated_tools):
                        t = accumulated_tools[i]
                        try:
                            args = json.loads(t.get("arguments", "{}") or "{}")
                        except Exception:
                            args = {}
                        chunk_tools.append({"name": t.get("name", ""), "args": args, "id": t.get("id", "")})
                    accumulated_tools.clear()
                    yield text_chunk, chunk_tools, finish_reason
                else:
                    yield text_chunk, [], ""

    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            msg = json.loads(body_text).get("error", {}).get("message", body_text)
        except Exception:
            msg = body_text
        if e.code == 429:
            raise RateLimitError(e.code, msg)
        if e.code >= 500:
            raise ServerError(e.code, msg)
        raise OpenRouterAPIError(e.code, msg)
    except urllib.error.URLError as e:
        raise OpenRouterAPIError(0, f"ネットワークエラー: {e.reason}")



# ── diff 表示ユーティリティ ───────────────────────────────────────

def _print_write_diff(fn_name: str, fn_args: dict) -> None:
    path = fn_args.get("path", "?")
    safe_print(C.gray(f"  [{fn_name}] → {path}"))


# ── OpenRouterAgent ───────────────────────────────────────────────

class OpenRouterAgent:
    """ReAct ループエージェント（OpenRouter版）。"""

    COMPACTION_THRESHOLD_CHARS = 3_000_000  # OwlAlpha 1Mトークン ≈ 400万文字の75%
    COMPACTION_KEEP_RECENT = 20

    def __init__(self, config_or_rotator, tool_registry):
        # AccountRotator でも OpenRouterConfig でも受け付ける
        if isinstance(config_or_rotator, AccountRotator):
            self._config = config_or_rotator._config
        elif isinstance(config_or_rotator, OpenRouterConfig):
            self._config = config_or_rotator
        else:
            raise TypeError(f"Unsupported config type: {type(config_or_rotator)}")

        self.rotator = AccountRotator(self._config)
        self.tools = tool_registry
        self.conversation: list[dict] = []
        self.system_prompt: Optional[str] = self._config.system_prompt or None
        self.thinking_enabled: bool = True
        self.cwd: str = str(Path.cwd().resolve())
        self._task_goal: Optional[str] = None
        self._tool_cache: dict[str, str] = {}
        self._tool_cache_lock = threading.Lock()
        self.json_mode: bool = False

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def set_thinking(self, enabled: bool, silent: bool = False):
        self.thinking_enabled = enabled
        if not silent:
            safe_print(f"  推論モード: {'ON' if enabled else 'OFF'}")

    def _build_context_header(self) -> str:
        return f"[作業フォルダ] {self.cwd}"

    def set_cwd(self, path: str):
        self.cwd = path
        safe_print(f"  作業フォルダを変更: {path}")

    def start_task(self, goal: str):
        self._task_goal = goal

    def end_task(self):
        self._task_goal = None

    def _task_context(self) -> str:
        if not self._task_goal:
            return ""
        return f"[現在のタスク] {self._task_goal}"

    def clear_history(self):
        self.conversation = []

    def print_status(self):
        n = len(self._config.api_keys)
        safe_print(f"  モデル  : {self._config.model}")
        safe_print(f"  APIキー : {n} 個")
        safe_print(f"  RPM上限 : {self._config.rpm_limit} / キー")
        for i, bucket in enumerate(self._config._buckets):
            tokens = round(bucket.tokens_available, 2)
            safe_print(f"    key_{i+1}: 残トークン {tokens}/{self._config.rpm_limit}")
        safe_print(f"  会話履歴: {len(self.conversation)} メッセージ")
        safe_print(f"  作業Dir : {self.cwd}")

    def _compact_if_needed(self):
        total_chars = sum(_msg_char_count(m) for m in self.conversation)
        if total_chars <= self.COMPACTION_THRESHOLD_CHARS:
            return
        keep_recent = self.COMPACTION_KEEP_RECENT
        first_pair = self.conversation[:2]
        recent_part = self.conversation[-keep_recent:] if keep_recent < len(self.conversation) else []
        removed = len(self.conversation) - len(first_pair) - len(recent_part)
        note = {"role": "user", "content": f"[{removed}件の古い会話を削除しました（コンテキスト節約）]"}
        ack = {"role": "assistant", "content": "了解しました。"}
        self.conversation = first_pair + [note, ack] + recent_part

    def _api_call_with_retry(
        self,
        messages: list[dict],
        override_tool_specs: Optional[list] = None,
    ) -> dict:
        tool_specs = override_tool_specs if override_tool_specs is not None else self.tools.get_specs()
        attempt = 0
        trim_count = 0
        working_messages = _repair_message_sequence(list(messages))

        while attempt < MAX_RETRIES:
            try:
                safe_print(C.gray(f"  → openrouter ({self._config.model})"), flush=True)
                response = _call_openrouter_api(
                    self._config, working_messages, tool_specs,
                    system_prompt=self.system_prompt,
                    json_mode=self.json_mode,
                )
                return response

            except RateLimitError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF)
                safe_print(C.yellow(f"  ⚠ 429 レート制限 → {backoff:.0f}秒待機してリトライ"), flush=True)
                time.sleep(backoff)
                attempt += 1

            except ServerError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2), MAX_BACKOFF)
                safe_print(C.yellow(f"  ⚠ サーバーエラー({e.status}): {e.message[:100]}"), flush=True)
                if len(working_messages) > 4 and trim_count < 5:
                    working_messages = _trim_messages_smart(working_messages)
                    trim_count += 1
                time.sleep(backoff)
                attempt += 1

            except OpenRouterAPIError as e:
                safe_print(C.red(f"  ✗ APIエラー({e.status}): {e.message}"), flush=True)
                raise

            except (http.client.RemoteDisconnected, ConnectionResetError, ConnectionError, TimeoutError) as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2), MAX_BACKOFF)
                safe_print(C.yellow(f"  ⚠ 接続エラー → {backoff:.0f}秒待機 ({type(e).__name__})"), flush=True)
                time.sleep(backoff)
                attempt += 1

        raise RuntimeError(f"API最大リトライ数({MAX_RETRIES})を超えました")

    def _stream_react_call(
        self,
        messages: list,
        text_callback=None,
    ) -> tuple[str, list]:
        """ストリーミング ReAct 呼び出し。(full_text, tool_calls) を返す。"""
        tool_specs = self.tools.get_specs()
        attempt = 0
        trim_count = 0
        working_messages = _repair_message_sequence(list(messages))

        while attempt < MAX_RETRIES:
            try:
                safe_print(C.gray(f"  → openrouter ({self._config.model})"), flush=True)
                full_text = ""
                tool_calls_list: list[dict] = []
                header_printed = False

                try:
                    for text_chunk, chunk_tools, finish_reason in _stream_openrouter_api(
                        self._config, working_messages, tool_specs, self.system_prompt,
                        json_mode=self.json_mode,
                    ):
                        if text_chunk:
                            if not header_printed:
                                safe_print(f"\n  {C.purple('💭')} ", end="", flush=True)
                                header_printed = True
                            if text_callback is not None:
                                text_callback(text_chunk)
                            else:
                                safe_print(C.purple(text_chunk), end="", flush=True)
                            full_text += text_chunk
                        for ct in chunk_tools:
                            if ct.get("name"):
                                tool_calls_list.append({"name": ct["name"], "args": dict(ct.get("args", {})), "id": ct.get("id", "")})
                except KeyboardInterrupt:
                    safe_print(C.yellow("\n\n  [割り込み] Ctrl+C"), flush=True)
                    return "__interrupted__", []

                if header_printed and text_callback is None:
                    safe_print()

                return full_text, tool_calls_list

            except RateLimitError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1), MAX_BACKOFF)
                safe_print(C.yellow(f"  ⚠ 429 → {backoff:.0f}秒待機 ({e.message[:80]})"), flush=True)
                time.sleep(backoff)
                attempt += 1

            except ServerError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2), MAX_BACKOFF)
                safe_print(C.yellow(f"  ⚠ サーバーエラー({e.status}) → {backoff:.0f}秒待機"), flush=True)
                if len(working_messages) > 4 and trim_count < 5:
                    working_messages = _trim_messages_smart(working_messages)
                    trim_count += 1
                time.sleep(backoff)
                attempt += 1

            except OpenRouterAPIError as e:
                safe_print(C.red(f"  ✗ APIエラー({e.status}): {e.message}"), flush=True)
                raise

            except (http.client.RemoteDisconnected, ConnectionResetError, ConnectionError, TimeoutError) as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2), MAX_BACKOFF)
                safe_print(C.yellow(f"  ⚠ 接続エラー → {backoff:.0f}秒待機"), flush=True)
                time.sleep(backoff)
                attempt += 1

        raise RuntimeError(f"ストリーミングAPI最大リトライ数({MAX_RETRIES})を超えました")

    def _extract_text(self, response: dict) -> Optional[str]:
        try:
            return response["choices"][0]["message"].get("content") or None
        except (KeyError, IndexError):
            return None

    def _extract_tool_calls(self, response: dict) -> list[dict]:
        try:
            tcs = response["choices"][0]["message"].get("tool_calls") or []
            result = []
            for tc in tcs:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}") or "{}")
                except Exception:
                    args = {}
                result.append({
                    "name": fn.get("name", ""),
                    "args": args,
                    "id": tc.get("id", ""),
                })
            return result
        except (KeyError, IndexError):
            return []

    def _finish_reason(self, response: dict) -> str:
        try:
            reason = response["choices"][0].get("finish_reason") or "UNKNOWN"
            mapping = {"stop": "STOP", "tool_calls": "STOP", "length": "MAX_TOKENS"}
            return mapping.get(reason, reason.upper())
        except (KeyError, IndexError):
            return "UNKNOWN"

    def _make_cache_key(self, fn_name: str, fn_args: dict) -> str:
        return f"{fn_name}:{json.dumps(fn_args, sort_keys=True, ensure_ascii=False)}"

    def _invalidate_cache_for_path(self, path: str):
        parent_dir = str(Path(path).parent)
        dir_key = self._make_cache_key("list_directory", {"path": parent_dir})
        with self._tool_cache_lock:
            for key in list(self._tool_cache):
                if key.startswith("read_file:") and json.dumps(path) in key:
                    self._tool_cache.pop(key, None)
                elif key == dir_key:
                    self._tool_cache.pop(key, None)

    def _run_single_tool(self, tc: dict) -> tuple[str, str]:
        fn_name = tc.get("name", "")
        fn_args = tc.get("args", {})
        call_id = tc.get("id", f"call_{fn_name}")

        cache_key = self._make_cache_key(fn_name, fn_args)
        if fn_name in _CACHEABLE_TOOLS:
            with self._tool_cache_lock:
                if cache_key in self._tool_cache:
                    return self._tool_cache[cache_key], call_id

        tool = self.tools._tools.get(fn_name)
        if not tool:
            result = f"[エラー] ツール '{fn_name}' が見つかりません"
        else:
            try:
                result = tool["fn"](**fn_args)
                if result is None:
                    result = "(完了)"
                result = str(result)
            except Exception as e:
                result = f"[エラー] {fn_name}: {e}\n{traceback.format_exc()}"

        # 書き込み系ツールのキャッシュ無効化
        if fn_name in ("write_file", "edit_file", "patch_file", "delete_file"):
            path = fn_args.get("path", "")
            if path:
                self._invalidate_cache_for_path(path)

        if fn_name in _CACHEABLE_TOOLS:
            with self._tool_cache_lock:
                self._tool_cache[cache_key] = result

        return result, call_id

    def run_stream(self, user_message: str, callback=None) -> str:
        """Interactive モードと同じ表示エンジン（ストリーミング + PipelineTypewriter）で
        ReAct ループを実行する。callback は後方互換のために受け取るが使用しない。"""
        from .utils import PipelineTypewriter
        from .tools import clear_read_files_registry, UserRejectedWriteError
        from uuid import uuid4

        clear_read_files_registry()
        self._compact_if_needed()

        ctx_parts = [p for p in [self._build_context_header(), self._task_context()] if p]
        injected = ("\n\n".join(ctx_parts) + "\n\n" + user_message) if ctx_parts else user_message

        messages: list[dict] = list(self.conversation)
        old_conv_len = len(self.conversation)
        messages.append({"role": "user", "content": injected})

        write_tools = {"write_file", "edit_file", "patch_file", "delete_file"}

        for _ in range(MAX_TOOL_ROUNDS):
            _tw = PipelineTypewriter()
            _tw.start()
            text, tool_calls = self._stream_react_call(messages, text_callback=_tw.feed)
            _tw.finalize()

            if text == "__interrupted__":
                return "処理を中断しました。"

            if not tool_calls:
                final = text or "(応答なし)"
                self.conversation.append({"role": "user", "content": user_message})
                self.conversation.extend(messages[old_conv_len + 1:])
                self.conversation.append({"role": "assistant", "content": final})
                return final

            messages.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {
                        "id": tc.get("id") or f"call_{tc['name']}_{uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                fn_name = tc.get("name", "")
                fn_args = tc.get("args", {})
                call_id = tc.get("id") or f"call_{fn_name}_{uuid4().hex[:8]}"

                safe_print(
                    f"  {C.bold_green('⚙')} {C.green(fn_name)}"
                    + C.cyan(f"({', '.join(f'{k}={repr(v)[:40]}' for k, v in fn_args.items())})"),
                    flush=True,
                )

                if fn_name in ("write_file", "edit_file", "patch_file"):
                    _print_write_diff(fn_name, fn_args)

                try:
                    result = self.tools.execute(fn_name, fn_args)
                    result_str = cache_tool_output(fn_name, str(result))
                    if fn_name in _CACHEABLE_TOOLS:
                        cache_key = self._make_cache_key(fn_name, fn_args)
                        self._tool_cache[cache_key] = result_str
                    elif fn_name in write_tools:
                        self._invalidate_cache_for_path(fn_args.get("path", ""))
                except UserRejectedWriteError:
                    raise
                except Exception as e:
                    result_str = f"ツール実行エラー: {fn_name}: {e}"
                    safe_print(C.red(f"\n  ✗ [{fn_name}] エラー: {e}"), flush=True)

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result_str,
                })

        fallback = f"(ReActループ上限 {MAX_TOOL_ROUNDS} ターンに達しました)"
        self.conversation.append({"role": "user", "content": user_message})
        self.conversation.extend(messages[old_conv_len + 1:])
        self.conversation.append({"role": "assistant", "content": fallback})
        return fallback

    def run(self, user_message: str) -> str:
        """ReAct ループを実行して最終回答を返す。"""
        from .tools import clear_read_files_registry
        clear_read_files_registry()
        self._compact_if_needed()

        ctx_parts = [p for p in [self._build_context_header(), self._task_context()] if p]
        injected = user_message
        if ctx_parts:
            injected = "\n".join(ctx_parts) + "\n\n" + user_message

        self.conversation.append({"role": "user", "content": injected})

        for round_num in range(MAX_TOOL_ROUNDS):
            response = self._api_call_with_retry(self.conversation)
            text = self._extract_text(response)
            tool_calls = self._extract_tool_calls(response)
            finish = self._finish_reason(response)

            if text:
                safe_print(f"\n  {C.purple('💭')} {C.purple(text)}")

            if not tool_calls:
                final = text or "(応答なし)"
                self.conversation.append({"role": "assistant", "content": final})
                return final

            # アシスタントメッセージを OpenAI ネイティブ形式で記録
            self.conversation.append({
                "role": "assistant",
                "content": text or None,
                "tool_calls": [
                    {
                        "id": tc.get("id") or f"call_{tc['name']}_{uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # 並列ツール実行
            results = []
            if len(tool_calls) == 1:
                result, call_id = self._run_single_tool(tool_calls[0])
                safe_print(C.gray(f"  🔧 {tool_calls[0]['name']} → {str(result)[:80]}"))
                results.append({"call_id": call_id, "result": result})
            else:
                with ThreadPoolExecutor(max_workers=min(len(tool_calls), 4)) as ex:
                    futures = {ex.submit(self._run_single_tool, tc): tc for tc in tool_calls}
                    for future in as_completed(futures):
                        tc = futures[future]
                        result, call_id = future.result()
                        safe_print(C.gray(f"  🔧 {tc['name']} → {str(result)[:80]}"))
                        results.append({"call_id": call_id, "result": result})

            # ツール結果を OpenAI ネイティブ形式（role: tool）で追加
            for r in results:
                self.conversation.append({
                    "role": "tool",
                    "tool_call_id": r["call_id"],
                    "content": r["result"],
                })

        return "(最大ツール呼び出し回数に達しました)"
