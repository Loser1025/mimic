"""
unilive/voice_agent.py
────────────────────────────────────────────────────────────────
Live API ブリッジ — V4 フルスタック統合版

■ アーキテクチャ
    マイク ──→ Live API (推論・ツール決定) ──→ スピーカー
                       ↕  tool_call
                  V4ToolExecutor
                    ├─ キャッシュ（read系）
                    ├─ 書き込み前 diff 表示 + 確認
                    ├─ 削除前確認
                    ├─ エラー自動リトライ + ユーザー介入
                    ├─ AutoGit バックアップ / チェックポイント
                    ├─ 並列ツール実行（read系）
                    ├─ 長い出力の AI 要約
                    └─ ReactLog 記録
                  LongTermMemory (RAG)
                    ├─ ターン開始時に関連教訓を注入
                    ├─ ターン完了後に新規教訓を抽出
                    └─ 注入教訓のフィードバック更新

■ 起動方法
    python voice_agent.py           # 音声モード
    python voice_agent.py --text    # テキストモード（動作確認用）

■ テキストモードのコマンド
    /log    ReActログを表示
    /undo   AutoGit でロールバック
    /diff   バックアップからの差分を表示
    exit    終了
"""

import asyncio
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ─── V4 をインポート ─────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

print("  V4 を読み込み中...", flush=True)
try:
    import V4 as _v4
except ImportError as e:
    print(f"[エラー] V4.py のインポートに失敗しました: {e}")
    sys.exit(1)

_tools      = _v4.tools
_AutoGit    = _v4.AutoGit
_ReactLog   = _v4.ReactLog
_LTM        = _v4.LongTermMemory
_CACHEABLE  = _v4._CACHEABLE_TOOLS
_print_diff = _v4._print_write_diff
_OUT_LIMIT  = _v4.TOOL_OUTPUT_LIMIT
_compress   = _v4._compress_lesson
C           = _v4.C
safe_print  = _v4.safe_print

_WRITE_TOOLS = {"write_file", "edit_file", "patch_file", "delete_file"}
_SKIP_TOOLS  = {"ask_user"}

# lessons_db.json は V4.py と同じフォルダを優先、なければ unilive/
_LTM_PATH = str(_HERE / "lessons_db.json")
if not Path(_LTM_PATH).exists():
    _v4_db = _HERE / "lessons_db.json"
    _LTM_PATH = str(_v4_db)


# ─── 設定読み込み ────────────────────────────────────────────────

def load_config() -> dict:
    env_path = _HERE / ".env"
    if not env_path.exists():
        print("[エラー] .env ファイルが見つかりません。")
        print("  .env.template をコピーして GEMINI_KEY_1 を設定してください。")
        sys.exit(1)

    cfg: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip().strip('"\'')

    api_key = cfg.get("GEMINI_KEY_1", "")
    if not api_key or api_key.startswith("YOUR_"):
        print("[エラー] .env の GEMINI_KEY_1 にAPIキーが設定されていません。")
        sys.exit(1)

    return {
        "api_key":       api_key,
        "model":         cfg.get("LIVE_MODEL",    "gemini-3.1-flash-live-preview"),
        "voice_name":    cfg.get("VOICE_NAME",    "Kore"),
        "system_prompt": cfg.get("SYSTEM_PROMPT",
            "あなたは日本語で話す高機能AIエージェントです。"
            "ユーザーの指示に従い、必要に応じてツールを使ってタスクを実行します。"
            "実行前に何をするか簡潔に説明してから行動してください。"
        ),
        "cwd": cfg.get("WORK_DIR", str(Path.cwd())),
    }


# ─── Gemini 通常 API ヘルパー（要約・教訓抽出用）────────────────

def _gemini_generate(api_key: str, prompt: str) -> str:
    """
    Gemini 通常 API（非 Live）で1回の生成を行う。
    要約・教訓抽出などのバックグラウンドタスクに使用。
    """
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=prompt,
    )
    return response.text or ""


# ─── V4 ツール実行パイプライン ────────────────────────────────────

class V4ToolExecutor:
    """
    V4 InteractiveOrchestrator の全ツール実行機能を Live API ブリッジ向けに移植。

    実装済み V4 機能:
      ✓ 読み取り系ツールのキャッシュ
      ✓ write/edit/patch 実行前の diff 表示 + 確認
      ✓ delete 実行前の確認
      ✓ エラー自動リトライ + ユーザー介入（MAX_AUTO_RETRY 回）
      ✓ AutoGit バックアップ / チェックポイント
      ✓ 長いツール出力の AI 要約（失敗時は truncate フォールバック）
      ✓ 読み取り系ツールの並列実行（ThreadPoolExecutor）
      ✓ ReactLog への action / observation 記録
      ✓ RAG（LongTermMemory）への注入 / 教訓抽出 / フィードバック
    """

    MAX_AUTO_RETRY = _v4.InteractiveOrchestrator.MAX_AUTO_RETRY  # 2

    def __init__(self, cwd: str, api_key: str, ltm: "_v4.LongTermMemory"):
        self.cwd       = cwd
        self.api_key   = api_key
        self.ltm       = ltm
        self.auto_git  = _AutoGit()
        self.react_log = _ReactLog()
        self._cache:     dict[str, str] = {}
        self._err_count: dict[str, int] = {}

    # ── AutoGit ─────────────────────────────────────────────────

    def backup(self):
        result = self.auto_git.backup(self.cwd)
        safe_print(C.gray(f"  [AutoGit] {result}"), flush=True)

    def rollback(self) -> str:
        return self.auto_git.rollback(self.cwd)

    def diff(self) -> str:
        return self.auto_git.diff(self.cwd)

    def _checkpoint(self, tool: str, path: str = ""):
        self.auto_git.checkpoint(self.cwd, tool, path)

    # ── キャッシュ ───────────────────────────────────────────────

    def _cache_key(self, name: str, args: dict) -> str:
        return f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"

    def _invalidate_cache(self, path: str):
        path_json = json.dumps(path, ensure_ascii=False)
        self._cache = {k: v for k, v in self._cache.items() if path_json not in k}

    # ── AI 要約 ──────────────────────────────────────────────────

    def _summarize(self, tool_name: str, text: str) -> str:
        """TOOL_OUTPUT_LIMIT を超えた出力を Gemini API で要約する。"""
        if len(text) <= _OUT_LIMIT:
            return text
        safe_print(C.gray(
            f"  [要約] {tool_name} の出力が長いため要約します "
            f"({len(text):,}文字 → 上限 {_OUT_LIMIT:,}文字)..."
        ), flush=True)
        try:
            summary = _gemini_generate(
                self.api_key,
                f"以下はツール「{tool_name}」の実行結果です。"
                f"重要な情報をすべて保持しつつ3000文字以内で要約してください。\n\n"
                f"{text[:50000]}"
            )
            if not summary:
                raise ValueError("空の要約レスポンス")
            safe_print(C.gray(f"  [要約完了] {len(summary):,}文字"), flush=True)
            return summary
        except Exception as e:
            safe_print(C.yellow(f"  [要約失敗] truncate にフォールバック: {e}"), flush=True)
            return text[:_OUT_LIMIT] + f"\n… (省略: 全{len(text):,}文字)"

    # ── 確認ダイアログ ───────────────────────────────────────────

    def _confirm_write(self, fn_name: str, fn_args: dict) -> str | None:
        try:
            _print_diff(fn_name, fn_args)
        except Exception:
            pass
        safe_print(C.yellow(f"\n  [書き込み確認] {fn_name} を実行しますか？"), flush=True)
        safe_print(C.gray("    y または Enter → 実行 / n → スキップ"), flush=True)
        try:
            ans = input(C.bold_green("  >>> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "[ユーザーがキャンセル]"
        return None if ans not in ("n", "no") else f"[スキップ] {fn_name} はスキップされました"

    def _confirm_delete(self, path: str) -> str | None:
        safe_print(C.red(f"\n  [⚠ 削除確認] {path} を削除します"), flush=True)
        safe_print(C.gray("    y または Enter → 削除実行 / n → スキップ"), flush=True)
        try:
            ans = input(C.bold_green("  >>> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "[ユーザーがキャンセル]"
        return None if ans not in ("n", "no") else "[スキップ] delete_file はスキップされました"

    # ── 単一ツール実行 ───────────────────────────────────────────

    def _execute_one(self, fn_name: str, fn_args: dict) -> str:
        """
        1ツールを実行する（確認・キャッシュ・リトライ・要約付き）。
        並列実行・逐次実行の両方から呼ばれる。
        """
        # キャッシュ確認（読み取り系のみ）
        if fn_name in _CACHEABLE:
            key = self._cache_key(fn_name, fn_args)
            if key in self._cache:
                cached = self._cache[key]
                safe_print(C.gray(f"    [キャッシュ] {len(cached):,}文字"), flush=True)
                return cached

        # 書き込み・削除の確認（逐次実行時のみ。並列中は write ツールを呼ばない）
        if fn_name in ("write_file", "edit_file", "patch_file"):
            msg = self._confirm_write(fn_name, fn_args)
            if msg:
                return msg
        elif fn_name == "delete_file":
            msg = self._confirm_delete(fn_args.get("path", "?"))
            if msg:
                return msg

        # 実行（エラーリトライ付き）
        while True:
            try:
                raw = _tools.execute(fn_name, fn_args)
                result = self._summarize(fn_name, str(raw) if raw is not None else "(完了)")

                # キャッシュ登録 / 書き込み後の無効化 + チェックポイント
                if fn_name in _CACHEABLE:
                    self._cache[self._cache_key(fn_name, fn_args)] = result
                elif fn_name in ("write_file", "edit_file", "patch_file"):
                    self._invalidate_cache(fn_args.get("path", ""))
                    self._checkpoint(fn_name, fn_args.get("path", ""))

                self._err_count[fn_name] = 0
                return result

            except Exception as e:
                err_msg = str(e)
                self._err_count[fn_name] = self._err_count.get(fn_name, 0) + 1
                safe_print(C.red(f"\n  ✗ [{fn_name}] エラー: {err_msg}"), flush=True)

                if self._err_count[fn_name] < self.MAX_AUTO_RETRY:
                    return f"ツール実行エラー: {fn_name}: {err_msg}"

                # リトライ上限超過 → ユーザー介入
                safe_print(C.yellow(
                    f"\n  ⚠ {self.MAX_AUTO_RETRY} 回連続エラー。手動介入が必要です。"
                ), flush=True)
                safe_print(C.gray("    r → リトライ / c → スキップ / その他 → AI への追加指示"), flush=True)
                try:
                    choice = input(C.bold_green("  >>> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    return f"[キャンセル] {err_msg}"

                if choice.lower() == "r":
                    self._err_count[fn_name] = 0
                    continue
                elif choice.lower() == "c":
                    return f"[スキップ] エラー: {err_msg}"
                else:
                    return f"[ユーザー指示] {choice}\n[元のエラー] {err_msg}"

    # ── バッチ実行（並列 / 逐次を自動判定）──────────────────────

    def execute_batch(self, tool_calls: list[dict]) -> list[tuple[str, str]]:
        """
        複数ツールを実行して [(fn_name, result), ...] を返す。
        書き込み系ツールが含まれる場合は逐次、読み取り系のみなら並列。
        """
        has_write = any(tc["name"] in _WRITE_TOOLS for tc in tool_calls)

        if len(tool_calls) > 1 and not has_write:
            # ── 並列実行 ─────────────────────────────────────────
            safe_print(C.cyan(f"\n  ⚡ {len(tool_calls)} ツールを並列実行"), flush=True)
            results: list[tuple[str, str]] = [("", "")] * len(tool_calls)

            def _par_exec(idx_tc):
                idx, tc = idx_tc
                fn_name = tc["name"]
                fn_args = tc.get("args", {})
                self.react_log.add("action", tool=fn_name,
                                   args=_v4.InteractiveOrchestrator._fmt_args(fn_args),
                                   step=len(self.react_log.entries))
                r = self._execute_one(fn_name, fn_args)
                self.react_log.add("observation", tool=fn_name,
                                   result=r[:150], step=len(self.react_log.entries))
                return idx, fn_name, r

            with ThreadPoolExecutor(max_workers=len(tool_calls)) as ex:
                futs = [ex.submit(_par_exec, (i, tc)) for i, tc in enumerate(tool_calls)]
                for fut in as_completed(futs):
                    idx, fn_name, r = fut.result()
                    results[idx] = (fn_name, r)
            return results
        else:
            # ── 逐次実行 ─────────────────────────────────────────
            out = []
            for tc in tool_calls:
                fn_name = tc["name"]
                fn_args = tc.get("args", {})
                self.react_log.add("action", tool=fn_name,
                                   args=_v4.InteractiveOrchestrator._fmt_args(fn_args),
                                   step=len(self.react_log.entries))
                r = self._execute_one(fn_name, fn_args)
                self.react_log.add("observation", tool=fn_name,
                                   result=r[:150], step=len(self.react_log.entries))
                out.append((fn_name, r))
            return out

    # ── RAG: 教訓注入 ────────────────────────────────────────────

    def inject_rag(self, user_message: str) -> tuple[str, list[str]]:
        """
        LongTermMemory から関連教訓を取得してメッセージ先頭に注入する。
        戻り値: (augmented_message, injected_lesson_texts)
        """
        if not self.ltm:
            return user_message, []
        try:
            lessons = self.ltm.retrieve_relevant_lessons(user_message, self.api_key)
            if not lessons:
                return user_message, []

            compressed = [_compress(e.get("lesson", "")) for e in lessons]
            texts      = [e.get("lesson", "") for e in lessons]

            safe_print(C.bold_mem(
                f"\n  🧠 長期記憶から {len(lessons)} 件の教訓をロードしました"
            ), flush=True)
            for l in compressed:
                safe_print(C.mem(f"     • {l}"), flush=True)

            block = "\n".join(f"- {l}" for l in compressed)
            aug   = f"[過去の類似タスクからの教訓]\n{block}\n\n{user_message}"
            return aug, texts

        except Exception as e:
            safe_print(C.yellow(f"  [RAG] 教訓取得エラー: {e}"), flush=True)
            return user_message, []

    # ── RAG: タスク完了後の教訓抽出・フィードバック ──────────────

    def post_task(
        self, user_message: str, final_response: str, injected_lessons: list[str]
    ) -> None:
        """
        タスク完了後にバックグラウンドで実行する。
        1. 注入した教訓の有効性を判定して use_count/fail_count を更新
        2. 新規教訓を抽出して LongTermMemory に追記
        """
        if not self.ltm:
            return

        def _run():
            try:
                # ── 1. 注入教訓のフィードバック ──────────────────
                if injected_lessons:
                    list_str = "\n".join(f"- {l}" for l in injected_lessons)
                    eval_raw = _gemini_generate(
                        self.api_key,
                        f"[タスク]\n{user_message[:500]}\n\n"
                        f"[最終回答]\n{final_response[:1000]}\n\n"
                        f"[注入された教訓]\n{list_str}\n\n"
                        "上記の各教訓が今回の回答を導くのに実際に役立ったかを判定し、"
                        "以下のJSON形式のみで出力してください。\n"
                        '{"helpful": ["本文"], "unhelpful": ["本文"]}'
                    )
                    m = re.search(r'\{.*\}', eval_raw, re.DOTALL)
                    if m:
                        try:
                            d = json.loads(m.group())
                            for t in d.get("helpful",   []):
                                self.ltm.update_lesson_feedback(t, is_helpful=True)
                            for t in d.get("unhelpful", []):
                                self.ltm.update_lesson_feedback(t, is_helpful=False)
                        except Exception:
                            pass

                # ── 2. 新規教訓の抽出 ────────────────────────────
                lesson_raw = _gemini_generate(
                    self.api_key,
                    f"[タスク]\n{user_message[:500]}\n\n"
                    f"[最終結果の要約]\n{final_response[:1000]}\n\n"
                    "このタスクと結果から、今後の同種タスクで役立つ技術的な教訓や"
                    "エラー回避の事実を1つだけ簡潔に抽出してください。"
                    "教訓がない場合は「なし」とだけ出力してください。"
                )
                lesson = lesson_raw.strip()
                if lesson and lesson not in ("なし", "なし。"):
                    self.ltm.add_lesson(user_message, lesson, self.api_key)
                    preview = lesson[:80] + ("..." if len(lesson) > 80 else "")
                    safe_print(C.bold_mem(f"\n  💡 新しい教訓を記憶しました"), flush=True)
                    safe_print(C.mem(f"     {preview}"), flush=True)

            except Exception as e:
                safe_print(C.yellow(f"  [教訓抽出] エラー: {e}"), flush=True)

        # バックグラウンドスレッドで実行（メインループをブロックしない）
        threading.Thread(target=_run, daemon=True).start()


# ─── google-genai ツール定義の構築 ───────────────────────────────

def build_genai_tools() -> list:
    from google.genai import types
    declarations = []
    for spec in _tools.get_specs():
        if spec["name"] in _SKIP_TOOLS:
            continue
        try:
            declarations.append(types.FunctionDeclaration(
                name=spec["name"],
                description=spec["description"],
                parameters=spec.get("parameters", {"type": "object", "properties": {}}),
            ))
        except Exception as e:
            safe_print(C.yellow(f"  [警告] ツール '{spec['name']}' 変換失敗: {e}"), flush=True)
    safe_print(C.gray(f"  ツール登録: {len(declarations)} 件"), flush=True)
    return [types.Tool(function_declarations=declarations)]


def build_system_prompt(base: str, cwd: str, ltm: "_v4.LongTermMemory") -> str:
    """
    Live API 向けシステムプロンプトを構築する。
    V4 の REACT_SYSTEM_PROMPT をベースに、音声モード向けに調整。
    全教訓を上位10件プリロードして RAG のベースラインとする（音声モード用）。
    """
    # V4 の REACT_SYSTEM_PROMPT から音声向けに調整（ask_user 指示を除外）
    react_core = (
        "## 思考の構造化\n"
        "行動前に状況を分析し、実行計画を立ててから行動してください。\n\n"
        "## 作業ルール\n"
        "- プロジェクト構造が不明な場合はまず get_repo_map で全体像を把握する\n"
        "- ファイル編集前に必ず read_file で現在の内容を確認する\n"
        "- エラーが出たら原因を分析して対処策を実行する\n"
        "- 複数の独立した読み取り操作は同時に呼び出す（並列実行）\n"
        "- タスク完了時は結果を簡潔にまとめて終了する\n"
        "- 依頼されていない改善・最適化を自発的に行わない\n\n"
        "## ツール使用の禁止事項\n"
        "- 確認せずにファイルを上書き・削除しない\n"
        "- 推測だけで重要なファイル操作を行わない\n"
    )

    tool_list = "\n".join(
        f"  - {s['name']}: {s['description'][:70]}"
        for s in _tools.get_specs()
        if s["name"] not in _SKIP_TOOLS
    )

    # 長期記憶のトップ教訓を事前ロード（音声モードの RAG ベースライン）
    preloaded_lessons = ""
    if ltm:
        try:
            all_lessons = sorted(
                ltm._lessons,
                key=lambda x: x.get("use_count", 0),
                reverse=True,
            )[:10]
            if all_lessons:
                lesson_lines = "\n".join(
                    f"  - {_compress(e.get('lesson', ''))}" for e in all_lessons
                )
                preloaded_lessons = (
                    f"\n\n## 過去の教訓（参考）\n{lesson_lines}"
                )
        except Exception:
            pass

    return (
        f"{base}\n\n"
        f"## 作業フォルダ\n  {cwd}\n\n"
        f"{react_core}"
        f"\n## 利用可能なツール\n{tool_list}"
        f"{preloaded_lessons}\n\n"
        "## 音声モード専用ルール\n"
        "- すべての応答は日本語で行うこと\n"
        "- 音声で話しているので簡潔に答えること\n"
        "- ファイル書き込み・削除の前に必ず内容を説明し確認を取ること\n"
    )


# ─── ツール呼び出しハンドラ ───────────────────────────────────────

async def handle_tool_calls(session, tool_call, executor: V4ToolExecutor) -> None:
    from google.genai import types

    # tool_calls を [{name, args}, ...] 形式に整形
    calls = [
        {"name": fc.name, "args": dict(fc.args) if fc.args else {}}
        for fc in tool_call.function_calls
    ]

    # 表示
    for tc in calls:
        safe_print(C.cyan(f"\n  [ツール] {tc['name']}"), flush=True)
        if tc["args"]:
            preview = {k: (str(v)[:80] + "…" if len(str(v)) > 80 else v)
                       for k, v in tc["args"].items()}
            safe_print(C.gray(f"  [引数]  {preview}"), flush=True)

    # バッチ実行（並列 / 逐次を自動判定）
    # asyncio スレッドで実行して UI をブロックしない
    results = await asyncio.to_thread(executor.execute_batch, calls)

    # 結果を表示
    for fn_name, result in results:
        display = result[:200] + "…" if len(result) > 200 else result
        safe_print(C.cyan(f"  [結果]  {display}"), flush=True)

    # Live API にツール結果を返送
    function_responses = []
    for (fn_name, result), fc in zip(results, tool_call.function_calls):
        function_responses.append(types.FunctionResponse(
            name=fn_name, id=fc.id, response={"output": result}
        ))
    await session.send_tool_response(function_responses=function_responses)


# ─── テキストモード ───────────────────────────────────────────────

async def run_text_mode(cfg: dict) -> None:
    from google import genai
    from google.genai import types

    ltm      = _LTM(_LTM_PATH)
    executor = V4ToolExecutor(cfg["cwd"], cfg["api_key"], ltm)
    client   = genai.Client(api_key=cfg["api_key"],
                            http_options={"api_version": "v1alpha"})
    genai_tools = build_genai_tools()
    system_prompt = build_system_prompt(cfg["system_prompt"], cfg["cwd"], ltm)

    live_config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=system_prompt,
        tools=genai_tools,
    )

    safe_print(C.green(f"  モデル : {cfg['model']}"))
    safe_print(C.green(f"  モード : テキスト"))
    safe_print(C.green(f"  作業フォルダ: {cfg['cwd']}"))
    safe_print(C.gray("  接続中..."))

    async with client.aio.live.connect(model=cfg["model"], config=live_config) as session:
        executor.backup()
        safe_print(C.bold_green("  接続完了！\n"))
        safe_print(C.gray(
            "  メッセージ入力 → Enter  "
            "| /log でReActログ | /undo でロールバック | /diff で差分 | exit で終了\n"
        ))

        while True:
            try:
                raw_input = input(C.bold_green("あなた > ")).strip()
            except (EOFError, KeyboardInterrupt):
                safe_print(C.gray("\n  終了します。"))
                break

            if not raw_input:
                continue
            if raw_input.lower() in ("exit", "quit", "q"):
                safe_print(C.gray("  終了します。"))
                break

            # ── スラッシュコマンド ────────────────────────────────
            if raw_input == "/log":
                executor.react_log.display()
                continue
            if raw_input == "/undo":
                result = executor.rollback()
                safe_print(C.yellow(f"  [AutoGit] {result}"))
                continue
            if raw_input == "/diff":
                safe_print(executor.diff())
                continue

            # ── RAG 注入 ─────────────────────────────────────────
            augmented, injected_lessons = await asyncio.to_thread(
                executor.inject_rag, raw_input
            )

            # ── コンテキストヘッダー付加 ─────────────────────────
            ctx_header = f"[作業フォルダ] {executor.cwd}"
            message    = f"{ctx_header}\n\n{augmented}"

            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=message)]
                ),
                turn_complete=True,
            )

            safe_print(C.bold_purple("AI > "), end="", flush=True)
            full_response = []

            async for response in session.receive():
                if response.tool_call:
                    await handle_tool_calls(session, response.tool_call, executor)
                    safe_print(C.bold_purple("AI > "), end="", flush=True)
                if response.text:
                    safe_print(response.text, end="", flush=True)
                    full_response.append(response.text)
                if response.server_content and response.server_content.turn_complete:
                    break

            safe_print()

            # ── タスク完了後の教訓抽出（バックグラウンド）──────────
            final_text = "".join(full_response)
            if final_text and len(executor.react_log.entries) > 0:
                executor.post_task(raw_input, final_text, injected_lessons)


# ─── 音声モード ───────────────────────────────────────────────────

async def run_voice_mode(cfg: dict) -> None:
    try:
        import sounddevice as sd
    except ImportError:
        print("[エラー] sounddevice が未インストールです。pip install sounddevice を実行してください。")
        sys.exit(1)

    from google import genai
    from google.genai import types

    INPUT_RATE  = 16000
    OUTPUT_RATE = 24000
    CHUNK       = 1024

    ltm      = _LTM(_LTM_PATH)
    executor = V4ToolExecutor(cfg["cwd"], cfg["api_key"], ltm)
    client   = genai.Client(api_key=cfg["api_key"],
                            http_options={"api_version": "v1alpha"})
    genai_tools   = build_genai_tools()
    system_prompt = build_system_prompt(cfg["system_prompt"], cfg["cwd"], ltm)

    # RealtimeInputConfig（VAD 明示有効化）- SDK バージョンによって存在しない場合は省略
    _realtime_input_cfg = None
    try:
        _realtime_input_cfg = types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
        )
        safe_print(C.gray("  [DBG] RealtimeInputConfig OK"), flush=True)
    except Exception as _cfg_e:
        safe_print(C.yellow(f"  [DBG] RealtimeInputConfig 非対応、省略: {_cfg_e}"), flush=True)

    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name=cfg["voice_name"]
                )
            )
        ),
        **({"realtime_input_config": _realtime_input_cfg} if _realtime_input_cfg else {}),
        system_instruction=system_prompt,
        tools=genai_tools,
    )

    import queue as _queue_mod
    from websockets.exceptions import ConnectionClosedError as _WsClosedError

    safe_print(C.green(f"  モデル : {cfg['model']}"))
    safe_print(C.green(f"  声    : {cfg['voice_name']}"))
    safe_print(C.green(f"  作業フォルダ: {cfg['cwd']}"))

    loop = asyncio.get_event_loop()
    mic_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def mic_callback(indata, frames, time_info, status):
        loop.call_soon_threadsafe(mic_queue.put_nowait, bytes(indata))

    # 音声出力スレッド（asyncio と完全分離、セッション跨ぎで再利用）
    audio_out_q: "_queue_mod.Queue[bytes | None]" = _queue_mod.Queue()

    def _playback_thread():
        with sd.RawOutputStream(samplerate=OUTPUT_RATE, channels=1, dtype="int16") as out:
            while True:
                chunk = audio_out_q.get()
                if chunk is None:
                    break
                try:
                    out.write(chunk)
                except Exception:
                    pass

    pb_thread = threading.Thread(target=_playback_thread, daemon=True)
    pb_thread.start()

    # マイク入力ストリーム（セッション跨ぎで再利用）
    input_stream = sd.RawInputStream(
        samplerate=INPUT_RATE, channels=1, dtype="int16",
        blocksize=CHUNK, callback=mic_callback,
    )
    input_stream.start()

    retry = 0
    while True:
        # ── 自動再接続ループ ─────────────────────────────────────
        safe_print(C.gray("  接続中..." if retry == 0 else f"  再接続中... (試行 {retry})"))
        try:
            async with client.aio.live.connect(
                model=cfg["model"], config=live_config
            ) as session:
                if retry == 0:
                    executor.backup()
                retry = 0
                safe_print(C.bold_green("  接続完了！"))
                safe_print(C.gray("  話しかけてください。Ctrl+C で終了\n"))

                # バッファ（セッションごとにリセット）
                _cur_user: list[str] = []
                _cur_ai:   list[str] = []

                _send_count = [0]  # 送信チャンク数（デバッグ用）

                async def send_loop():
                    safe_print(C.gray("  [DBG] send_loop 開始"), flush=True)
                    while True:
                        pcm = await mic_queue.get()
                        _send_count[0] += 1
                        if _send_count[0] % 50 == 1:  # 50チャンクごとに表示
                            safe_print(C.gray(f"  [DBG] 送信中 chunk#{_send_count[0]}"), flush=True)
                        try:
                            await session.send_realtime_input(
                                audio=types.Blob(data=pcm, mime_type="audio/pcm")
                            )
                        except Exception as _e:
                            _es = str(_e).lower()
                            safe_print(C.yellow(f"  [DBG] send エラー: {type(_e).__name__}: {_e}"), flush=True)
                            if any(k in _es for k in (
                                "closed", "eof", "disconnect",
                                "1011", "1006", "keepalive",
                            )):
                                safe_print(C.yellow("  [DBG] send_loop 終了（接続切断）"), flush=True)
                                break
                            await asyncio.sleep(0.01)
                    safe_print(C.yellow("  [DBG] send_loop 終了"), flush=True)

                async def receive_loop():
                    _ai_buf: list[str] = []
                    _turn = 0
                    while True:
                        _turn += 1
                        safe_print(C.gray(f"  [DBG] receive: ターン{_turn} 待機開始"), flush=True)
                        _got_turn_complete = False
                        async for response in session.receive():
                            safe_print(C.gray(f"  [DBG] recv t{_turn}: sc={bool(response.server_content)} tool={bool(response.tool_call)} repr={repr(response)[:120].replace(chr(10),' ')}"), flush=True)

                            if response.tool_call:
                                await handle_tool_calls(session, response.tool_call, executor)
                                continue

                            sc = response.server_content
                            if not sc:
                                continue

                            if sc.model_turn:
                                for part in (sc.model_turn.parts or []):
                                    idata = getattr(part, "inline_data", None)
                                    if idata and getattr(idata, "data", None):
                                        audio_out_q.put(idata.data)

                            it = getattr(sc, "input_transcription", None)
                            if it:
                                t = getattr(it, "text", "").strip()
                                if t:
                                    _cur_user.append(t)

                            ot = getattr(sc, "output_transcription", None)
                            if ot:
                                t = getattr(ot, "text", "")
                                if t:
                                    _ai_buf.append(t)
                                    _cur_ai.append(t)

                            if getattr(sc, "turn_complete", False):
                                _got_turn_complete = True
                                user_text = "".join(_cur_user).strip()
                                ai_text   = "".join(_ai_buf).strip()
                                if user_text:
                                    safe_print(C.gray(f"\n  [あなた] {user_text}"), flush=True)
                                if ai_text:
                                    safe_print(f"  {C.bold_purple('[AI]')} {ai_text}", flush=True)
                                if user_text and ai_text and len(executor.react_log.entries) > 0:
                                    executor.post_task(user_text, "".join(_cur_ai), [])
                                _cur_user.clear()
                                _cur_ai.clear()
                                _ai_buf.clear()
                                break
                        if _got_turn_complete:
                            safe_print(C.gray(f"  [DBG] receive: ターン{_turn} 完了→次のターンへ"), flush=True)
                            await asyncio.sleep(0)
                            continue
                        else:
                            safe_print(C.yellow(f"  [DBG] receive: ターン{_turn} ジェネレータ終了（turn_completeなし）→ 再接続"), flush=True)
                            break
                await asyncio.gather(send_loop(), receive_loop())

        except (KeyboardInterrupt, asyncio.CancelledError):
            break
        except Exception as e:
            err_str = str(e).lower()
            _retryable = (
                isinstance(e, _WsClosedError)
                or any(k in err_str for k in (
                    "keepalive", "ping timeout", "connection closed",
                    "reset by peer", "broken pipe", "eof", "service unavailable",
                    "1011", "1006",
                ))
            )
            if not _retryable:
                raise
            retry += 1
            if retry > 5:
                safe_print(C.red("  再接続上限(5回)に達しました。終了します。"))
                break
            wait = min(2 ** retry, 30)
            safe_print(C.yellow(f"  接続が切れました（{type(e).__name__}: {e}）。{wait}秒後に再接続します..."))
            await asyncio.sleep(wait)
            continue

    input_stream.stop()
    input_stream.close()
    audio_out_q.put(None)
    pb_thread.join(timeout=2)


# ─── エントリーポイント ───────────────────────────────────────────

def print_header():
    safe_print()
    safe_print(C.bold_green("  ┌──────────────────────────────────────────────────────┐"))
    safe_print(C.bold_green("  │   UNIMOG Voice — Gemini Live API + V4 Full Stack v2   │"))
    safe_print(C.bold_green("  └──────────────────────────────────────────────────────┘"))
    safe_print()
    safe_print(C.gray("  実装済み V4 機能:"))
    safe_print(C.gray("    ✓ ツールキャッシュ（read系）"))
    safe_print(C.gray("    ✓ 書き込み前 diff + 確認 / 削除前確認"))
    safe_print(C.gray("    ✓ エラー自動リトライ + ユーザー介入"))
    safe_print(C.gray("    ✓ AutoGit バックアップ / チェックポイント / rollback / diff"))
    safe_print(C.gray("    ✓ 長い出力の AI 要約（失敗時 truncate フォールバック）"))
    safe_print(C.gray("    ✓ 並列ツール実行（read 系、ThreadPoolExecutor）"))
    safe_print(C.gray("    ✓ ReactLog（/log で表示）"))
    safe_print(C.gray("    ✓ RAG 教訓注入（ターン開始時）"))
    safe_print(C.gray("    ✓ 新規教訓の自動抽出・保存（ターン完了後、バックグラウンド）"))
    safe_print(C.gray("    ✓ 注入教訓のフィードバック更新（helpful/unhelpful）"))
    safe_print(C.gray("    ✓ REACT_SYSTEM_PROMPT 相当のプロンプト適用"))
    safe_print(C.gray("    ✓ 作業フォルダコンテキスト注入"))
    safe_print()


def main():
    print_header()
    cfg       = load_config()
    text_mode = "--text" in sys.argv

    try:
        if text_mode:
            asyncio.run(run_text_mode(cfg))
        else:
            asyncio.run(run_voice_mode(cfg))
    except KeyboardInterrupt:
        safe_print(C.gray("\n  終了しました。"))
    except Exception as e:
        safe_print(C.red(f"\n  [エラー] {type(e).__name__}: {e}"))
        safe_print(C.gray("\n  ヒント:"))
        safe_print(C.gray("    接続エラー    → .env の GEMINI_KEY_1 を確認"))
        safe_print(C.gray("    音声デバイス  → python voice_agent.py --text で動作確認"))
        safe_print(C.gray("    モデルエラー  → .env の LIVE_MODEL を gemini-2.0-flash-live-001 に変更"))
        raise


if __name__ == "__main__":
    main()
