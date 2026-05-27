"""
mcp_server.py  —  mimic3 MCP Server (Full-Agent Edition)
==========================================================
Claude Code (推論) ← MCP → このサーバー → mimic3 フルエージェント

Claude の役割: ユーザー意図を理解して agent_run を呼ぶだけ
mimic3 の役割: OpenRouter ReAct ループ + AutoGit + 全ツール実行

起動: python -m mimic3.mcp_server  (tamalabo/ ディレクトリで実行)
      Claude Code の settings.json からは以下のように設定する:
        "command": "python",
        "args": ["-m", "mimic3.mcp_server"],
        "cwd": "<tamalabo のフルパス>"
"""

import asyncio
import logging
import re
import subprocess
import sys
from pathlib import Path

V4_DIR = Path(__file__).parent.parent

# ── MCP ─────────────────────────────────────────────────────────
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("mimic")

# ── ログ監視ウィンドウ管理 ───────────────────────────────────────
_monitor_launched: bool = False
_LOG_PATH = str(Path(__file__).parent / "mimic.log")

def _ensure_log_monitor():
    """
    ログ監視 PowerShell ウィンドウを1回だけ起動する。
    すでに起動済みの場合は何もしない。
    CREATE_NEW_CONSOLE で独立した新しいコンソールウィンドウを開く。
    """
    global _monitor_launched
    if _monitor_launched:
        return
    try:
        # クォート問題を避けるため EncodedCommand を使用
        import base64
        inner = f"Get-Content -Path '{_LOG_PATH}' -Wait -Tail 20 -Encoding UTF8"
        encoded = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
        subprocess.Popen(
            ["powershell", "-NoExit", "-NoProfile", "-EncodedCommand", encoded],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            close_fds=True,
        )
        _monitor_launched = True
    except Exception:
        pass  # 起動失敗は無視（監視ウィンドウはオプション機能）

# MCP から除外するツール（stdin 必須 / MCP 文脈で不要）
_EXCLUDE = {"ask_user"}

# ANSI エスケープコード除去
_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ════════════════════════════════════════════════════════════════
# ツール一覧
# ════════════════════════════════════════════════════════════════
@server.list_tools()
async def list_tools() -> list[Tool]:
    result: list[Tool] = []

    # ── ① メインツール: フルエージェント実行（最優先で使う）────────
    result.append(Tool(
        name="agent_run",
        description=(
            "【最優先】タスクを V4.py の Gemini フルエージェントに委譲して実行する。\n"
            "\n"
            "内部で実行されること:\n"
            "  • AutoGit バックアップ（タスク前に自動コミット）\n"
            "  • OpenRouter ReAct ループ（Thought→Action→Observation 最大60ステップ）\n"
            "  • ファイル編集・PowerShell・Web検索・Wikipedia など全ツール自動実行\n"
            "  • 並列ツール実行対応\n"
            "  • AutoGit チェックポイント（書き込み後に自動コミット）\n"
            "\n"
            "使い分け:\n"
            "  agent_run   → コーディング・ファイル編集・調査・マルチステップ作業\n"
            "  agent_plan  → 複雑なプロジェクト（計画→並列実行→レビュー）\n"
            "  個別ツール  → 単純な読み取り確認のみ"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "V4.py エージェントに実行させるタスクの詳細な説明（日本語OK）"
                },
                "working_dir": {
                    "type": "string",
                    "description": "作業ディレクトリのフルパス。省略時は V4.py と同じフォルダ"
                },
                "timeout": {
                    "type": "integer",
                    "description": "タイムアウト秒数（デフォルト 600 = 10分）",
                    "default": 600
                }
            },
            "required": ["task"]
        }
    ))

    # ── ② ターミナル起動（長時間・ユーザー監視が必要な作業）────────
    result.append(Tool(
        name="agent_terminal",
        description=(
            "V4.py を新しいターミナルウィンドウで起動する（インタラクティブモード）。\n"
            "30分以上かかる作業・ユーザーが途中で確認したい場合に使う。\n"
            "このツールは起動だけして即返す（結果待ちなし）。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "ターミナルに表示する初期タスクメモ（参照用）"
                },
                "working_dir": {
                    "type": "string",
                    "description": "作業ディレクトリのフルパス"
                }
            },
            "required": ["task"]
        }
    ))

    return result


# ════════════════════════════════════════════════════════════════
# ツール実行
# ════════════════════════════════════════════════════════════════
@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    loop = asyncio.get_event_loop()

    if name == "agent_run":
        result = await loop.run_in_executor(
            None, _agent_run,
            arguments.get("task", ""),
            arguments.get("working_dir"),
            arguments.get("timeout", 600),
            False,  # plan_mode=False
        )
        return [TextContent(type="text", text=result)]

    if name == "agent_terminal":
        result = _agent_terminal(
            arguments.get("task", ""),
            arguments.get("working_dir"),
        )
        return [TextContent(type="text", text=result)]

    return [TextContent(type="text", text=f"未知のツール: {name}")]


# ════════════════════════════════════════════════════════════════
# agent_run / agent_plan 実装
# ════════════════════════════════════════════════════════════════
def _agent_run(task: str, working_dir: str | None,
               timeout: int, plan_mode: bool) -> str:
    """
    V4.py を --auto-prompt（または /plan 相当）で起動して結果を返す。
    --auto-prompt モード:
      InteractiveOrchestrator.run_react() をフルで実行
      AutoGit + ReAct ループ + 全ツール
      ユーザー確認なし（自動承認）
    """
    _ensure_log_monitor()   # タスク開始時にログ監視ウィンドウを起動（初回のみ）

    cwd     = working_dir or str(V4_DIR)
    py      = sys.executable

    if plan_mode:
        # /plan モード: タスクの先頭に /plan を付けて --auto-prompt に渡す
        task_arg = f"/plan {task}"
    else:
        task_arg = task

    flag = "--auto-prompt"

    # 作業ディレクトリを mimic3 に伝える
    env_patch = {
        "MIMIC_CWD": cwd,
    }
    import os
    env = {
        **os.environ,
        **env_patch,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }

    DONE_MARKER = "===MIMIC_DONE==="
    import threading, time

    try:
        proc = subprocess.Popen(
            [py, "-m", "mimic3", flag, task_arg],
            stdin=subprocess.DEVNULL,   # MCP stdio を汚染させない
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # stderr も stdout にまとめてキャプチャ
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except Exception as e:
        return f"mimic3 起動エラー: {type(e).__name__}: {e}"

    result_lines: list[str] = []
    done_event = threading.Event()

    def _read():
        """stdout を行単位で読む。マーカーを検出したら即 done_event をセット。"""
        collecting = True
        try:
            for raw in proc.stdout:
                clean = strip_ansi(raw)
                if DONE_MARKER in clean:
                    done_event.set()
                    collecting = False
                    # V4.py がバックグラウンドで教訓保存中 → 読み捨てて排出
                    continue
                if collecting:
                    result_lines.append(clean)
        finally:
            done_event.set()  # EOF でも必ずセット

    reader = threading.Thread(target=_read, daemon=True)
    reader.start()

    if done_event.wait(timeout=timeout):
        answer = "".join(result_lines).strip()
        return answer or "(mimic3 の出力なし)"
    else:
        proc.kill()
        proc.wait()
        partial = "".join(result_lines).strip()
        return (
            f"タイムアウト ({timeout}秒)\n"
            f"途中出力:\n{partial[-2000:] if partial else '(なし)'}\n\n"
            f"長時間タスクは agent_terminal を使ってターミナルで実行してください。"
        )


# ════════════════════════════════════════════════════════════════
# agent_terminal 実装
# ════════════════════════════════════════════════════════════════
def _agent_terminal(task: str, working_dir: str | None) -> str:
    """新しい cmd ウィンドウで mimic3 をインタラクティブ起動"""
    cwd   = working_dir or str(V4_DIR)
    py    = sys.executable
    title = "Mimic — Agent Terminal"

    task_preview = task[:300].replace('"', "'")

    cmd = f'start "{title}" cmd /k "cd /d {V4_DIR} && {py} -m mimic3"'
    try:
        subprocess.Popen(cmd, shell=True, cwd=cwd)
        return (
            f"mimic3 ターミナルを起動しました。\n"
            f"作業フォルダ: {cwd}\n\n"
            f"以下のタスクをターミナルに貼り付けてください:\n"
            f"{'─'*50}\n"
            f"{task_preview}\n"
            f"{'─'*50}"
        )
    except Exception as e:
        return f"ターミナル起動エラー: {e}"


# ════════════════════════════════════════════════════════════════
# エントリポイント
# ════════════════════════════════════════════════════════════════
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

if __name__ == "__main__":
    asyncio.run(main())
