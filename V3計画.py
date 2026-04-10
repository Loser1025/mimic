"""
V3計画.py
=========
Gemini マルチアカウント ハイブリッド AI エージェント (unimog3)

動作モード:
  Interactive (ReAct) モード — デフォルト
    Thought → Action → Observation のループで1ステップずつ実行。
    初回アクション前にユーザー承認を求め、エラー時に介入を促す。
    Auto-Git によるバックアップ・チェックポイント・ロールバックに対応。

  Plan-and-Execute モード (/mode plan または /plan <タスク>)
    Planner がステップに分解 → Executor が実行 →
    Reviewer が検証・リトライ → Reflector が最終確認。
    独立ステップは ThreadPoolExecutor で並列実行。

共通機能:
- 複数アカウントのキーローテーション（最大9アカウント）
- Token Bucket (GCRA) + RPD デュアルレート制限
    RPM: Token Bucket 方式 — 毎分補充・即時ブロック不要
    RPD: 日次カウンタ — 上限回数を正確に管理
- 429 / 503 に対する指数バックオフ + ジッター自動リトライ
- PowerShell との安全な連携（UTF-8 BOM なし、exit code 制御）
- AI 要約によるセッション記憶（50万文字超で自動圧縮）
- JSON 構造化ログ
"""

import json
import time
import random
import sys
import os
import logging
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
import re
import difflib
import urllib.request
import urllib.error
import urllib.parse
import http.client


# ──────────────────────────────────────────────
# ANSIカラーヘルパー（VSCode / Windows Terminal対応）
# ──────────────────────────────────────────────

class C:
    """Matrix Green Theme (All colors unified to Green system)"""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    # --- ネオンカラー定義 (Green系統) ---
    _RG     = "\033[38;2;0;255;0m"      # Razer Green (メイン)
    _RG_DIM = "\033[38;2;0;64;0m"       # Dark Forest (枠線)
    _WHITE  = "\033[38;2;220;255;220m"  # Mint White (重要テキスト)
    _GRAY   = "\033[38;2;80;120;80m"    # Moss Gray (ログ)
    _PURPLE = "\033[38;2;160;255;120m"  # Pale Lime (AIの思考)
    _CYAN   = "\033[38;2;0;255;180m"    # Seafoam Green (観察・ツール結果)
    _RED    = "\033[38;2;200;255;0m"    # Toxic Yellow (エラー)
    _YELLOW = "\033[38;2;140;255;0m"    # Chartreuse (警告・待機)
    _ORANGE = "\033[38;2;0;200;100m"    # Emerald (並列処理)
    @staticmethod
    def green(s):      return f"{C._RG}{s}{C.RESET}"
    @staticmethod
    def green_dim(s):  return f"{C._RG_DIM}{s}{C.RESET}"
    @staticmethod
    def white(s):      return f"{C._WHITE}{s}{C.RESET}"
    @staticmethod
    def gray(s):       return f"{C._GRAY}{s}{C.RESET}"
    @staticmethod
    def red(s):        return f"{C._RED}{s}{C.RESET}"
    @staticmethod
    def yellow(s):     return f"{C._YELLOW}{s}{C.RESET}"
    @staticmethod
    def cyan(s):       return f"{C._CYAN}{s}{C.RESET}"
    @staticmethod
    def purple(s):     return f"{C._PURPLE}{s}{C.RESET}"
    @staticmethod
    def orange(s):     return f"{C._ORANGE}{s}{C.RESET}"
    @staticmethod
    def dim(s):        return f"{C.DIM}{s}{C.RESET}"
    @staticmethod
    def bold(s):       return f"{C.BOLD}{s}{C.RESET}"
    @staticmethod
    def bold_green(s): return f"{C.BOLD}{C._RG}{s}{C.RESET}"
    @staticmethod
    def bold_cyan(s):  return f"{C.BOLD}{C._CYAN}{s}{C.RESET}"
    @staticmethod
    def bold_purple(s):return f"{C.BOLD}{C._PURPLE}{s}{C.RESET}"


# ──────────────────────────────────────────────
# 簡易 Markdown → ANSI レンダラー
# ──────────────────────────────────────────────

def render_markdown(text: str) -> str:
    """
    Markdown テキストを ANSI エスケープコードに変換する。
    対応: 見出し / 太字 / 斜体 / インラインコード / コードブロック /
          箇条書き / 番号リスト / 水平線
    """
    lines = text.split("\n")
    out = []
    in_code_block = False
    code_lang = ""

    for line in lines:
        # ── コードブロック ─────────────────────────────
        if line.startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lang = line[3:].strip()
                label = f" {code_lang}" if code_lang else ""
                out.append(C.green_dim(f"┌─code{label}"))
            else:
                in_code_block = False
                out.append(C.green_dim("└─"))
            continue

        if in_code_block:
            out.append(f"  {C._RG_DIM}{line}{C.RESET}")
            continue

        # ── 水平線 ─────────────────────────────────────
        if re.match(r"^[-*_]{3,}$", line.strip()):
            out.append(C.green_dim("─" * 40))
            continue

        # ── 見出し ─────────────────────────────────────
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            title = _render_inline(m.group(2))
            if level == 1:
                out.append(C.bold_green(f"\n{title}"))
                out.append(C.green("─" * min(len(title) + 2, 50)))
            elif level == 2:
                out.append(C.bold_green(f"\n{title}"))
            elif level == 3:
                out.append(C.green(f"{title}"))
            else:
                out.append(C.gray(f"{title}"))
            continue

        # ── 箇条書き ────────────────────────────────────
        m = re.match(r"^(\s*)[-*+]\s+(.*)", line)
        if m:
            indent = len(m.group(1)) // 2
            bullet = ["•", "◦", "▸"][min(indent, 2)]
            out.append(f"{'  ' * indent}  {C.green(bullet)} {_render_inline(m.group(2))}")
            continue

        # ── 番号リスト ──────────────────────────────────
        m = re.match(r"^(\s*)(\d+)\.\s+(.*)", line)
        if m:
            indent = len(m.group(1)) // 2
            num = m.group(2)
            out.append(f"{'  ' * indent}  {C.green(num + '.')} {_render_inline(m.group(3))}")
            continue

        # ── 通常行 ──────────────────────────────────────
        out.append(_render_inline(line))

    return "\n".join(out)


def _render_inline(text: str) -> str:
    """インライン要素を変換する（Green / White / Cyan 限定版）"""
    # インラインコード `code` -> Razer Green
    text = re.sub(r"`([^`]+)`",
                  lambda m: f"{C._RG}{m.group(1)}{C.RESET}", text)
    
    # 太字 **text** -> 白の太字 (最も見やすい)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__",
                  lambda m: f"{C.BOLD}{C._WHITE}{m.group(1) or m.group(2)}{C.RESET}", text)
    
    # 斜体 *text* -> シアンの暗め表示
    text = re.sub(r"\*(.+?)\*|_(.+?)_",
                  lambda m: f"{C._PURPLE}{C.DIM}{m.group(1) or m.group(2)}{C.RESET}", text)
    return text


def print_ascii_art():
    art = f"""
{C._RG}   __  _   _  ___  __  __  ___   ___  __   __ ____ 
{C._RG}  / / | | | ||_ _||  \/  |/ _ \ / __| \ \ / /|__ / 
{C._PURPLE} / _ \| |_| | | | | |\/| | (_) | (_ |  \   /  |_ \ 
{C._CYAN} \___/ \___/ |___||_|  |_|\___/ \___|   |_|  |___/ 
{C.gray(" ────────────────────────────────────────────────── ")}
{C.bold_green(" UNIMOG 3.0.0 - THE HYBRID AI AGENT ")}
{C.gray(" ────────────────────────────────────────────────── ")}
    """
    print(art, flush=True)


# ──────────────────────────────────────────────
# ロギング設定（JSON 構造化ログ）
# ──────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)

def setup_logger(log_file: Optional[str] = None) -> logging.Logger:
    logger = logging.getLogger("gemini_agent")
    logger.setLevel(logging.DEBUG)
    fmt = JsonFormatter()

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger

log = setup_logger("gemini_agent.log")

# ──────────────────────────────────────────────
# データクラス
# ──────────────────────────────────────────────

class TokenBucket:
    """
    Token Bucket レートリミッター（RPM専用モード対応）

    ── RPM 制御: Token Bucket ──────────────────────────────────────
    バケツ容量  = rpm_limit トークン（例: 15）
    補充レート  = rpm_limit トークン / 60秒（例: 毎秒 0.25トークン）
    リクエストごとに 1 トークンを消費。

    ── RPD 制御: 日次カウンタ（オプション）────────────────────────
    rpd_limit=0 を指定すると RPD 無制限モード（Gemma 4 等に対応）。
    通常モデルは rpd_limit > 0 で日次上限を管理。

    ── スレッドセーフ ────────────────────────────────────────────────
    全操作を threading.Lock で保護。
    """

    RPD_UNLIMITED = 0  # RPD無制限を示す定数

    def __init__(self, rpm_limit: int = 15, rpd_limit: int = 1500):
        self.rpm_limit = rpm_limit
        self.rpd_limit = rpd_limit  # 0 = 無制限

        self._tokens: float = float(rpm_limit)
        self._last_refill: float = time.monotonic()
        self._refill_rate: float = rpm_limit / 60.0

        # RPD カウンタ（無制限モードでも記録だけはする）
        self._rpd_count: int = 0
        self._rpd_reset_at: datetime = self._next_utc_midnight()

        self._lock = threading.Lock()

    @staticmethod
    def _next_utc_midnight() -> datetime:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    def _refill(self, now_mono: float):
        elapsed = now_mono - self._last_refill
        self._tokens = min(
            float(self.rpm_limit),
            self._tokens + elapsed * self._refill_rate
        )
        self._last_refill = now_mono

    def _check_rpd_reset(self, now_utc: datetime):
        if now_utc >= self._rpd_reset_at:
            self._rpd_count = 0
            self._rpd_reset_at = self._next_utc_midnight()

    @property
    def rpd_unlimited(self) -> bool:
        return self.rpd_limit == self.RPD_UNLIMITED

    def acquire(self) -> tuple[bool, float]:
        """
        トークンを1枚取得しようとする。

        Returns:
            (True, 0.0)           取得成功
            (False, wait_sec)     RPM 不足 → wait_sec 秒後に再挑戦
            (False, float('inf')) RPD 枯渇 → 今日は使用不可（無制限モード時は発生しない）
        """
        with self._lock:
            now_mono = time.monotonic()
            now_utc  = datetime.now(timezone.utc).replace(tzinfo=None)

            self._check_rpd_reset(now_utc)

            # RPD チェック（無制限モードはスキップ）
            if not self.rpd_unlimited and self._rpd_count >= self.rpd_limit:
                return False, float("inf")

            self._refill(now_mono)

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._rpd_count += 1
                return True, 0.0

            wait = (1.0 - self._tokens) / self._refill_rate
            return False, wait

    def wait_time(self) -> float:
        with self._lock:
            now_mono = time.monotonic()
            elapsed = now_mono - self._last_refill
            projected = min(
                float(self.rpm_limit),
                self._tokens + elapsed * self._refill_rate
            )
            if projected >= 1.0:
                return 0.0
            return (1.0 - projected) / self._refill_rate

    @property
    def rpd_remaining(self) -> int:
        with self._lock:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            self._check_rpd_reset(now_utc)
            if self.rpd_unlimited:
                return -1  # -1 = 無制限を示す
            return max(0, self.rpd_limit - self._rpd_count)

    @property
    def tokens_available(self) -> float:
        """現在の利用可能トークン数（表示用）"""
        with self._lock:
            now_mono = time.monotonic()
            elapsed = now_mono - self._last_refill
            return min(
                float(self.rpm_limit),
                self._tokens + elapsed * self._refill_rate
            )


@dataclass
class AccountConfig:
    """1 Gemini アカウントの設定"""
    name: str
    api_key: str
    model: str = "gemini-2.0-flash"
    rpm_limit: int = 15
    rpd_limit: int = 1500
    thinking_level: str = "HIGH"   # HIGH / MEDIUM / LOW / NONE
    bucket: TokenBucket = field(init=False)

    def __post_init__(self):
        self.bucket = TokenBucket(
            rpm_limit=self.rpm_limit,
            rpd_limit=self.rpd_limit,
        )

# ──────────────────────────────────────────────
# PortContext（claw-code の context.py 相当）
# ──────────────────────────────────────────────

@dataclass(frozen=True)
class PortContext:
    """作業フォルダの構造スナップショット（不変）"""
    cwd: Path
    py_file_count: int       # 再帰的な .py ファイル数
    has_tests: bool          # tests/ フォルダまたは test_*.py の存在
    has_config: bool         # .json / .env 系設定ファイルの存在
    top_files: tuple         # フォルダ直下の上位10件
    py_files: tuple          # 直下の .py ファイル（上位5件）
    cfg_files: tuple         # 直下の設定ファイル（上位5件）


def build_port_context(cwd: Path) -> PortContext:
    """作業フォルダを走査して PortContext を構築する"""
    try:
        top_files = tuple(
            e.name + ("/" if e.is_dir() else "")
            for e in sorted(cwd.iterdir(), key=lambda x: (x.is_file(), x.name))[:10]
        )
    except Exception:
        top_files = ()

    try:
        py_files = tuple(f.name for f in cwd.glob("*.py"))[:5]
        cfg_files = tuple(
            f.name for f in list(cwd.glob("*.json")) + list(cwd.glob("*.env*"))
        )[:5]
        py_file_count = sum(1 for p in cwd.rglob("*.py") if p.is_file())
        has_tests = (cwd / "tests").is_dir() or any(
            f.name.startswith("test_") for f in cwd.glob("*.py")
        )
    except Exception:
        py_files = cfg_files = ()
        py_file_count = 0
        has_tests = False

    return PortContext(
        cwd=cwd,
        py_file_count=py_file_count,
        has_tests=has_tests,
        has_config=bool(cfg_files),
        top_files=top_files,
        py_files=py_files,
        cfg_files=cfg_files,
    )


def render_port_context(ctx: PortContext) -> str:
    """PortContext をシステムプロンプト注入用テキストに変換する"""
    lines = ["[実行コンテキスト]", f"作業フォルダ: {ctx.cwd}"]
    if ctx.py_file_count:
        lines.append(f"Pythonファイル数: {ctx.py_file_count}（再帰）")
    if ctx.top_files:
        lines.append(f"フォルダ内容: {', '.join(ctx.top_files)}")
    if ctx.py_files:
        lines.append(f"Pythonファイル: {', '.join(ctx.py_files)}")
    if ctx.cfg_files:
        lines.append(f"設定ファイル: {', '.join(ctx.cfg_files)}")
    if ctx.has_tests:
        lines.append("テスト: あり（tests/ または test_*.py）")
    return "\n".join(lines)

# ──────────────────────────────────────────────
# ExecutionRegistry（claw-code の execution_registry.py 相当）
# ──────────────────────────────────────────────

class ExecutionRegistry:
    """
    スラッシュコマンドを登録・ルーティングするレジストリ。

    登録: @registry.register("name", "説明") デコレータ
    ルーティング: route("/name args") → (name, handler, args) または None

    handler のシグネチャ: fn(agent: GeminiAgent, args: str) -> None
    """

    def __init__(self):
        self._commands: dict[str, tuple[str, Any]] = {}  # name -> (description, handler)

    def register(self, name: str, description: str):
        def decorator(fn):
            self._commands[name.lower()] = (description, fn)
            return fn
        return decorator

    def route(self, text: str) -> Optional[tuple[str, Any, str]]:
        """
        スラッシュコマンドをパースしてハンドラを返す。
        Returns: (name, handler, remaining_args) or None
        """
        if not text.startswith("/"):
            return None
        parts = text[1:].split(maxsplit=1)
        key = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        if key in self._commands:
            _, handler = self._commands[key]
            return key, handler, args
        return None

    def help_text(self) -> str:
        lines = ["コマンド一覧:"]
        for name, (desc, _) in sorted(self._commands.items()):
            lines.append(f"  /{name:<20} - {desc}")
        lines.append("  exit                  - 終了")
        return "\n".join(lines)


# グローバルコマンドレジストリ
cmd_registry = ExecutionRegistry()

# ──────────────────────────────────────────────
# ツールシステム（claw-code の tool harness 相当）
# ──────────────────────────────────────────────

class ToolRegistry:
    """エージェントが使えるツールを管理"""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, parameters: dict):
        """ツールを登録"""
        def decorator(fn):
            self._tools[name] = {
                "fn": fn,
                "spec": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                }
            }
            return fn
        return decorator

    def get_specs(self) -> list[dict]:
        return [v["spec"] for v in self._tools.values()]

    def execute(self, name: str, args: dict) -> Any:
        if name not in self._tools:
            raise ValueError(f"未知のツール: {name}")
        log.info({"tool_call": name, "args": args})
        return self._tools[name]["fn"](**args)


# グローバルツールレジストリ
tools = ToolRegistry()


@tools.register(
    name="read_file",
    description=(
        "ローカルファイルの内容を読み取る。"
        "offset・limitで行範囲を指定可能（大きいファイルは必ず分割して読む）。"
        "例: offset=0, limit=100 で先頭100行、offset=100, limit=100 で次の100行。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":   {"type": "string",  "description": "読み取るファイルパス"},
            "offset": {"type": "integer", "description": "読み取り開始行番号（0始まり、省略時は先頭から）", "default": 0},
            "limit":  {"type": "integer", "description": "読み取る最大行数（省略時は全行）"},
        },
        "required": ["path"]
    }
)
def read_file(path: str, offset: int = 0, limit: Optional[int] = None) -> str:
    p = Path(path)
    if not p.exists():
        return f"エラー: ファイルが見つかりません: {path}"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    total = len(lines)
    sliced = lines[offset: offset + limit] if limit is not None else lines[offset:]
    if offset or limit is not None:
        end = offset + len(sliced)
        header = f"[{path}  行 {offset + 1}–{end} / 全{total}行]\n"
    else:
        header = ""
    return header + "".join(sliced)


@tools.register(
    name="write_file",
    description="ローカルファイルに内容を書き込む",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "書き込み先ファイルパス"},
            "content": {"type": "string", "description": "書き込む内容"}
        },
        "required": ["path", "content"]
    }
)
def write_file(path: str, content: str) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"書き込み完了: {path} ({len(content)} 文字)"


@tools.register(
    name="run_powershell",
    description=(
        "PowerShellコマンドを安全に実行して結果を返す。"
        "結果の先頭が [SUCCESS] なら成功、[FAILURE(ExitCode=N)] なら失敗。"
        "working_directory は必ず明示すること（省略時はPython起動フォルダ）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "command":           {"type": "string",  "description": "実行するPowerShellコマンド"},
            "timeout":           {"type": "integer", "description": "タイムアウト秒数（デフォルト60）", "default": 60},
            "working_directory": {"type": "string",  "description": "コマンドを実行する作業フォルダのフルパス（必ず指定）"},
        },
        "required": ["command"]
    }
)
def run_powershell(command: str, timeout: int = 60,
                   working_directory: str = None) -> str:
    import subprocess
    import tempfile
    cwd = working_directory or str(Path.cwd())
    # PS内でシングルクォートをエスケープ
    cwd_escaped = cwd.replace("'", "''")

    # UTF-8強制 + cwd注入 + エラー継続モードでコマンドをラップ
    wrapped = (
        "$OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\r\n"
        "$ErrorActionPreference = 'Continue'\r\n"
        f"Set-Location -LiteralPath '{cwd_escaped}'\r\n"
        f"{command}"
    )
    # 一時ファイルに書き出して -File で実行（-Command だと改行を含む長いコマンドが壊れる）
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ps1", delete=False,
            encoding="utf-8", newline="\r\n"
        ) as tmp:
            tmp.write(wrapped)
            tmp_path = tmp.name

        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", tmp_path],
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        rc  = result.returncode
        status = "SUCCESS" if rc == 0 else f"FAILURE(ExitCode={rc})"
        parts  = [f"[{status}]", f"作業フォルダ: {cwd}"]
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"[FAILURE(TIMEOUT)] {timeout}秒経過 — コマンドを分割するか timeout を延ばしてください"
    except FileNotFoundError:
        return "[FAILURE] PowerShellが見つかりません（Windowsで実行してください）"
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass


@tools.register(
    name="list_directory",
    description="ディレクトリの内容を一覧表示する",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "一覧表示するディレクトリパス"}
        },
        "required": ["path"]
    }
)
def list_directory(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"エラー: ディレクトリが見つかりません: {path}"
    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
    lines = []
    for e in entries:
        kind = "FILE" if e.is_file() else "DIR "
        size = f"{e.stat().st_size:>10}" if e.is_file() else "          "
        lines.append(f"{kind}  {size}  {e.name}")
    return f"--- {path} ({len(lines)} items) ---\n" + "\n".join(lines)


@tools.register(
    name="glob",
    description=(
        "ファイル名のglobパターンで一致するファイル・ディレクトリの一覧を返す。"
        "拡張子検索・ファイル名パターン検索に使う（内容検索はsearch_filesを使うこと）。"
        "例: pattern='**/*.py' で全Pythonファイル、'src/**/*.ts' でsrc以下のTypeScriptファイル。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern":     {"type": "string",  "description": "globパターン（例: **/*.py, src/**/*.ts, *.json）"},
            "path":        {"type": "string",  "description": "検索ルートディレクトリ（省略時はカレント）", "default": "."},
            "max_results": {"type": "integer", "description": "最大件数（デフォルト200）", "default": 200},
        },
        "required": ["pattern"]
    }
)
def glob_files(pattern: str, path: str = ".", max_results: int = 200) -> str:
    root = Path(path)
    if not root.exists():
        return f"エラー: ディレクトリが見つかりません: {path}"
    try:
        matches = sorted(root.glob(pattern))
    except Exception as e:
        return f"globエラー: {e}"
    if not matches:
        return f"「{pattern}」にマッチするファイルが見つかりませんでした。（検索: {path}）"
    lines = []
    for m in matches[:max_results]:
        kind = "DIR " if m.is_dir() else "FILE"
        try:
            rel = m.relative_to(root)
        except ValueError:
            rel = m
        size = f"{m.stat().st_size:>10}" if m.is_file() else "          "
        lines.append(f"{kind}  {size}  {rel}")
    truncated = len(matches) > max_results
    suffix = f"（先頭{max_results}件を表示、計{len(matches)}件）" if truncated else f"（計{len(matches)}件）"
    header = f"glob: 「{pattern}」 {suffix}  [{path}]\n"
    return header + "\n".join(lines)


@tools.register(
    name="edit_file",
    description="ファイルの特定部分を差分編集する。old_string を new_string に置き換える。ファイル全体の再書き込みより安全で正確。",
    parameters={
        "type": "object",
        "properties": {
            "path":       {"type": "string", "description": "編集するファイルパス"},
            "old_string": {"type": "string", "description": "置き換え対象の文字列（ファイル内で一意である必要あり）"},
            "new_string": {"type": "string", "description": "置き換え後の文字列"}
        },
        "required": ["path", "old_string", "new_string"]
    }
)
def edit_file(path: str, old_string: str, new_string: str) -> str:
    import difflib as _difflib
    p = Path(path)
    if not p.exists():
        return f"エラー: ファイルが見つかりません: {path}"
    content = p.read_text(encoding="utf-8", errors="replace")
    count = content.count(old_string)
    if count == 1:
        new_content = content.replace(old_string, new_string, 1)
        trailing = "\n" if content.endswith("\n") else ""
        p.write_text(new_content, encoding="utf-8")
        diff_lines = new_string.count("\n") - old_string.count("\n")
        sign = "+" if diff_lines >= 0 else ""
        return f"編集完了: {path}  ({sign}{diff_lines} 行差分, 計 {new_content.count(chr(10))+1} 行)"
    if count > 1:
        return (
            f"エラー: 指定した文字列が {count} 箇所に存在します（一意でない）。\n"
            f"前後の文脈をより多く含めた文字列を指定してください。"
        )
    # ── 完全一致なし → patch_file の類似マッチに委譲 ────────────
    # (edit_file は patch_file のエイリアスとして再呼び出し)
    return patch_file(path, old_string, new_string)


@tools.register(
    name="search_files",
    description=(
        "ディレクトリ配下のファイルをキーワード（正規表現）で全文検索する。grep相当。"
        "context_lines を指定するとマッチ行の前後 N 行も表示（grep -C 相当）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern":       {"type": "string",  "description": "検索する正規表現パターン"},
            "path":          {"type": "string",  "description": "検索対象のディレクトリパス（省略時はカレント）", "default": "."},
            "glob_pattern":  {"type": "string",  "description": "対象ファイルのglobフィルタ（例: *.py, **/*.txt）", "default": "**/*"},
            "max_results":   {"type": "integer", "description": "最大マッチ件数（context行は除く）", "default": 50},
            "context_lines": {"type": "integer", "description": "マッチ行の前後に表示する行数（grep -C 相当、デフォルト0）", "default": 0}
        },
        "required": ["pattern"]
    }
)
def search_files(pattern: str, path: str = ".", glob_pattern: str = "**/*",
                 max_results: int = 50, context_lines: int = 0) -> str:
    search_path = Path(path)
    if not search_path.exists():
        return f"エラー: パスが見つかりません: {path}"
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"正規表現エラー: {e}"

    results = []
    match_count = 0
    files_searched = 0
    skipped_binary = 0

    for file_path in sorted(search_path.glob(glob_pattern)):
        if not file_path.is_file():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="strict")
        except (UnicodeDecodeError, PermissionError):
            skipped_binary += 1
            continue

        files_searched += 1
        all_lines = content.splitlines()
        rel = file_path.relative_to(search_path) if file_path.is_relative_to(search_path) else file_path

        # コンテキスト行出力済み行番号を記録（重複出力防止）
        printed: set[int] = set()
        file_results: list[str] = []

        for lineno, line in enumerate(all_lines, 1):
            if regex.search(line):
                match_count += 1

                if context_lines > 0:
                    # 区切り線（前のマッチとの間に空白がある場合）
                    ctx_start = max(0, lineno - 1 - context_lines)
                    ctx_end   = min(len(all_lines), lineno + context_lines)
                    # 前のコンテキストとの間に gap があれば区切り追加
                    if printed and min(printed) > ctx_start and (ctx_start - 1) not in printed:
                        file_results.append(f"{rel}:---")
                    for i in range(ctx_start, ctx_end):
                        if i not in printed:
                            marker = ">" if i == lineno - 1 else " "
                            file_results.append(f"{rel}:{i+1}{marker} {all_lines[i].rstrip()}")
                            printed.add(i)
                else:
                    file_results.append(f"{rel}:{lineno}: {line.rstrip()}")

                if match_count >= max_results:
                    break

        results.extend(file_results)
        if match_count >= max_results:
            break

    if not results:
        note = f"（バイナリ/権限なし {skipped_binary} 件スキップ）" if skipped_binary else ""
        return f"「{pattern}」にマッチする行が見つかりませんでした。{note}（{files_searched} ファイル検索）"

    truncated = match_count >= max_results
    ctx_note = f", context={context_lines}" if context_lines > 0 else ""
    header = (
        f"検索: 「{pattern}」 — {match_count} 件{'以上' if truncated else ''}{ctx_note}  "
        f"({files_searched} ファイル検索)\n"
    )
    return header + "\n".join(results)


@tools.register(
    name="web_search",
    description="キーワードでWebを検索して結果（タイトル・URL・概要）を返す。DuckDuckGo使用、APIキー不要。",
    parameters={
        "type": "object",
        "properties": {
            "query":       {"type": "string",  "description": "検索クエリ"},
            "max_results": {"type": "integer", "description": "最大件数（デフォルト5）", "default": 5}
        },
        "required": ["query"]
    }
)
def web_search(query: str, max_results: int = 5) -> str:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    req = urllib.request.Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    })

    def _strip(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s).replace("&amp;", "&").replace("&#x2F;", "/").strip()

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"Web検索エラー: {e}"

    # DuckDuckGo HTML 構造: result__a (タイトル+href), result__snippet (概要)
    # href は /l/?uddg=<encoded_url> 形式のリダイレクト
    title_pat   = re.compile(r'class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
    snippet_pat = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)

    titles_urls = title_pat.findall(html)
    snippets    = [_strip(s) for s in snippet_pat.findall(html)]

    if not titles_urls:
        # フォールバック: href に uddg= が含まれる <a> を探す
        fallback = re.findall(r'href="(/l/\?uddg=[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
        titles_urls = fallback

    results = []
    for i, (href, title) in enumerate(titles_urls):
        if i >= max_results:
            break
        title_clean = _strip(title)
        # リダイレクトURLから実URLを復元
        uddg_m = re.search(r"uddg=([^&\"]+)", href)
        actual_url = urllib.parse.unquote(uddg_m.group(1)) if uddg_m else href
        snippet = snippets[i] if i < len(snippets) else ""
        results.append(f"[{i+1}] {title_clean}\n    {actual_url}\n    {snippet}")

    if not results:
        return f"「{query}」の検索結果が見つかりませんでした。"

    return f"Web検索: 「{query}」\n\n" + "\n\n".join(results)


@tools.register(
    name="fetch_webpage",
    description=(
        "URLのWebページを取得してテキストを抽出する。"
        "web_searchで得たURLの内容を詳しく読む・ドキュメントを参照する・記事全文を確認するのに使う。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "url":       {"type": "string",  "description": "取得するURL"},
            "max_chars": {"type": "integer", "description": "最大文字数（デフォルト10000）", "default": 10000}
        },
        "required": ["url"]
    }
)
def fetch_webpage(url: str, max_chars: int = 10000) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "")
            # charset 検出
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].strip().split(";")[0].strip()
            raw = resp.read()
    except Exception as e:
        return f"ページ取得エラー: {e}"

    try:
        html = raw.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        html = raw.decode("utf-8", errors="replace")

    # <script> <style> <nav> <footer> <header> を除去
    for tag in ("script", "style", "nav", "footer", "header", "aside"):
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", " ", html,
                      flags=re.DOTALL | re.IGNORECASE)
    # HTMLコメント除去
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)

    # タイトル抽出
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

    # タグを除去してテキスト化
    text = re.sub(r"<[^>]+>", " ", html)

    # HTML エンティティ変換
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">", "&nbsp;": " ",
        "&#39;": "'", "&quot;": '"', "&#x2F;": "/", "&apos;": "'",
    }
    for ent, char in entities.items():
        text = text.replace(ent, char)
    # 数値エンティティ（例: &#12354; → あ）
    text = re.sub(r"&#(\d+);",
                  lambda m: chr(int(m.group(1))) if int(m.group(1)) < 0x110000 else "", text)

    # 空白正規化
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    header = f"URL: {url}\n"
    if title:
        header += f"タイトル: {title}\n"
    header += "\n"

    body = text[:max_chars]
    suffix = f"\n\n... (全 {len(text):,} 文字中 {max_chars:,} 文字を表示)" if len(text) > max_chars else ""
    return header + body + suffix


@tools.register(
    name="wikipedia_search",
    description=(
        "Wikipediaで記事を検索して要約を取得する。"
        "事実確認・人物/企業/技術の概要調査に最適。APIキー不要・無制限。"
        "日本語と英語を切り替えられる。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query":       {"type": "string",  "description": "検索クエリ"},
            "lang":        {"type": "string",  "description": "言語コード（ja=日本語, en=英語）デフォルト: ja", "default": "ja"},
            "max_results": {"type": "integer", "description": "取得する記事数（デフォルト3）", "default": 3}
        },
        "required": ["query"]
    }
)
def wikipedia_search(query: str, lang: str = "ja", max_results: int = 3) -> str:
    # ── 1. 記事タイトルを検索 ────────────────────────────────────
    search_url = (
        f"https://{lang}.wikipedia.org/w/api.php?"
        f"action=query&list=search"
        f"&srsearch={urllib.parse.quote(query)}"
        f"&srlimit={max_results}&format=json&utf8=1"
    )
    req = urllib.request.Request(
        search_url,
        headers={"User-Agent": "unimog-agent/2.0 (personal assistant bot)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"Wikipedia検索エラー: {e}"

    hits = data.get("query", {}).get("search", [])
    if not hits:
        return f"「{query}」の記事が Wikipedia に見つかりませんでした。"

    # ── 2. 各記事の要約を取得（REST API）────────────────────────
    results = []
    for item in hits[:max_results]:
        title = item["title"]
        summary_url = (
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/"
            f"{urllib.parse.quote(title)}"
        )
        summary_req = urllib.request.Request(
            summary_url,
            headers={"User-Agent": "unimog-agent/2.0"}
        )
        try:
            with urllib.request.urlopen(summary_req, timeout=10) as resp:
                sd = json.loads(resp.read().decode("utf-8"))
            extract  = sd.get("extract", "")
            page_url = sd.get("content_urls", {}).get("desktop", {}).get("page", "")
        except Exception:
            # フォールバック: 検索スニペットを使用
            extract  = re.sub(r"<[^>]+>", "", item.get("snippet", "")).strip()
            page_url = (
                f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title)}"
            )

        results.append(
            f"【{title}】\n{extract[:800]}\nURL: {page_url}"
        )

    return f"Wikipedia: 「{query}」\n\n" + "\n\n".join(results)


@tools.register(
    name="ask_user",
    description=(
        "ユーザーに質問して回答を得る。"
        "不明な点・確認が必要な事項・選択肢の決定などに使用する。"
        "Interactive モードで有効。コンソールで入力を待機する。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "ユーザーへの質問内容"}
        },
        "required": ["question"]
    }
)
def ask_user(question: str) -> str:
    print(C.bold_purple(f"\n  [AIからの質問]"))
    print(C.purple(f"  {question}"))
    try:
        answer = input(C.bold_green("  >>> ")).strip()
    except (EOFError, KeyboardInterrupt):
        answer = "(キャンセルされました)"
    return answer or "(回答なし)"


@tools.register(
    name="patch_file",
    description=(
        "Search & Replace ブロック方式でファイルを編集する（Aider/Cline スタイル）。"
        "インデントのズレをある程度許容してマッチする。"
        "edit_file より耐障害性が高い。変更前に read_file で内容を確認すること。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path":    {"type": "string", "description": "編集するファイルパス"},
            "search":  {"type": "string", "description": "置き換え対象のコードブロック（前後の行を含めて一意にすること）"},
            "replace": {"type": "string", "description": "置き換え後のコードブロック"},
        },
        "required": ["path", "search", "replace"]
    }
)
def patch_file(path: str, search: str, replace: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"エラー: ファイルが見つかりません: {path}"
    content = p.read_text(encoding="utf-8", errors="replace")

    # ── 1. 完全一致を試みる ───────────────────────────────────────
    if search in content:
        count = content.count(search)
        if count > 1:
            return (
                f"エラー: 検索ブロックが {count} 箇所にマッチします（一意でない）。\n"
                f"前後の文脈をより多く含めた文字列を指定してください。"
            )
        new_content = content.replace(search, replace, 1)
        p.write_text(new_content, encoding="utf-8")
        diff_lines = replace.count("\n") - search.count("\n")
        sign = "+" if diff_lines >= 0 else ""
        return f"編集完了（完全一致）: {path}  ({sign}{diff_lines} 行差分)"

    # ── 2. インデント正規化後にファジーマッチ ────────────────────
    def strip_common_indent(text: str) -> tuple[str, int]:
        """共通インデントを除去して (正規化テキスト, インデント幅) を返す"""
        lines = text.splitlines()
        non_empty = [l for l in lines if l.strip()]
        if not non_empty:
            return text, 0
        min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
        stripped = "\n".join(
            l[min_indent:] if len(l) >= min_indent else l for l in lines
        )
        return stripped, min_indent

    content_lines = content.splitlines()
    s_stripped, s_indent = strip_common_indent(search)
    s_lines = s_stripped.splitlines()
    n = len(s_lines)

    def apply_and_write(content_lines: list, i: int, n: int,
                        block: str, b_indent: int) -> str:
        """マッチしたブロックを replace で置換してファイルに書く共通処理"""
        indent_delta = b_indent - s_indent
        r_stripped, _ = strip_common_indent(replace)
        r_lines = r_stripped.splitlines()
        if indent_delta >= 0:
            re_indented = "\n".join(
                " " * indent_delta + l if l.strip() else l for l in r_lines
            )
        else:
            r_min = min(
                (len(l) - len(l.lstrip()) for l in r_lines if l.strip()), default=0
            )
            trim = min(-indent_delta, r_min)
            re_indented = "\n".join(
                l[trim:] if len(l) >= trim else l for l in r_lines
            )
        new_lines = (content_lines[:i]
                     + re_indented.splitlines()
                     + content_lines[i + n:])
        trailing = "\n" if content.endswith("\n") else ""
        p.write_text("\n".join(new_lines) + trailing, encoding="utf-8")
        return re_indented, block

    for i in range(len(content_lines) - n + 1):
        block = "\n".join(content_lines[i:i + n])
        b_stripped, b_indent = strip_common_indent(block)
        if ([l.strip() for l in b_stripped.splitlines()] ==
                [l.strip() for l in s_lines]):
            re_indented, block = apply_and_write(content_lines, i, n, block, b_indent)
            diff_lines = re_indented.count("\n") - block.count("\n")
            sign = "+" if diff_lines >= 0 else ""
            return (
                f"編集完了（インデント許容マッチ）: {path}  "
                f"({sign}{diff_lines} 行差分, indent_delta={b_indent - s_indent:+})"
            )

    # ── 3. difflib SequenceMatcher による類似ブロック探索 ─────────
    import difflib
    s_key = [l.strip() for l in s_lines if l.strip()]  # 空行除いた比較キー
    best_ratio = 0.0
    best_i = -1
    best_n = n  # 検索行数 ±2 の範囲でウィンドウ幅を変えて探す
    THRESHOLD = 0.82

    for win in range(max(1, n - 2), n + 3):
        for i in range(len(content_lines) - win + 1):
            block_lines = content_lines[i:i + win]
            b_key = [l.strip() for l in block_lines if l.strip()]
            ratio = difflib.SequenceMatcher(None, s_key, b_key).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_i = i
                best_n = win

    if best_ratio >= THRESHOLD and best_i >= 0:
        block = "\n".join(content_lines[best_i:best_i + best_n])
        b_stripped, b_indent = strip_common_indent(block)
        re_indented, block = apply_and_write(
            content_lines, best_i, best_n, block, b_indent
        )
        diff_lines = re_indented.count("\n") - block.count("\n")
        sign = "+" if diff_lines >= 0 else ""
        return (
            f"編集完了（類似マッチ ratio={best_ratio:.2f}）: {path}  "
            f"({sign}{diff_lines} 行差分, line {best_i+1}–{best_i+best_n})"
        )

    preview = search[:120].replace("\n", "↵")
    hint = ""
    if best_ratio > 0:
        hint = f"\n最近似ブロック類似度: {best_ratio:.2f}（行 {best_i+1}–{best_i+best_n}）— 閾値 {THRESHOLD} 未満のため適用見送り"
    return (
        f"エラー: 検索ブロックがファイル内に見つかりません: {path}\n"
        f"検索ブロック（先頭120文字）: {preview}{hint}\n"
        f"ヒント: read_file でファイル内容を確認してから正確な文字列を指定してください。"
    )


@tools.register(
    name="delete_file",
    description=(
        "ファイルを削除する。**元に戻せない操作**。"
        "Auto-Git チェックポイントが自動作成されるため /undo で復元可能。"
        "ディレクトリは削除不可（run_powershell を使うこと）。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "削除するファイルパス"}
        },
        "required": ["path"]
    }
)
def delete_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"エラー: ファイルが見つかりません: {path}"
    if p.is_dir():
        return f"エラー: ディレクトリは削除できません（run_powershell で Remove-Item -Recurse を使うこと）: {path}"
    size = p.stat().st_size
    p.unlink()
    return f"削除完了: {path} ({size:,} バイト)"


@tools.register(
    name="create_directory",
    description="ディレクトリを作成する（親ディレクトリも含めて再帰的に作成）。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "作成するディレクトリパス"}
        },
        "required": ["path"]
    }
)
def create_directory(path: str) -> str:
    p = Path(path)
    if p.exists():
        return f"既に存在します: {path}"
    p.mkdir(parents=True, exist_ok=True)
    return f"ディレクトリ作成完了: {path}"


@tools.register(
    name="append_file",
    description="ファイルの末尾にテキストを追記する。ファイルが存在しない場合は新規作成。",
    parameters={
        "type": "object",
        "properties": {
            "path":    {"type": "string", "description": "追記先ファイルパス"},
            "content": {"type": "string", "description": "追記する内容"},
            "newline": {"type": "boolean", "description": "追記前に改行を挿入するか（デフォルト: true）", "default": True}
        },
        "required": ["path", "content"]
    }
)
def append_file(path: str, content: str, newline: bool = True) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    sep = "\n" if newline and existing and not existing.endswith("\n") else ""
    p.write_text(existing + sep + content, encoding="utf-8")
    return f"追記完了: {path} (+{len(content)} 文字)"


@tools.register(
    name="move_file",
    description="ファイルまたはディレクトリを移動・リネームする。",
    parameters={
        "type": "object",
        "properties": {
            "src":  {"type": "string", "description": "移動元のパス"},
            "dst":  {"type": "string", "description": "移動先のパス（ファイル名変更も可）"}
        },
        "required": ["src", "dst"]
    }
)
def move_file(src: str, dst: str) -> str:
    import shutil
    s, d = Path(src), Path(dst)
    if not s.exists():
        return f"エラー: 移動元が見つかりません: {src}"
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(s), str(d))
    return f"移動完了: {src} → {dst}"


@tools.register(
    name="copy_file",
    description="ファイルをコピーする（メタデータも保持）。",
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "コピー元のファイルパス"},
            "dst": {"type": "string", "description": "コピー先のファイルパス"}
        },
        "required": ["src", "dst"]
    }
)
def copy_file(src: str, dst: str) -> str:
    import shutil
    s, d = Path(src), Path(dst)
    if not s.exists():
        return f"エラー: コピー元が見つかりません: {src}"
    d.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(s), str(d))
    return f"コピー完了: {src} → {dst} ({s.stat().st_size} バイト)"


# ──────────────────────────────────────────────
# APIクライアント
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Auto-Git（バックアップ・チェックポイント・ロールバック）
# ──────────────────────────────────────────────

class AutoGit:
    """
    タスク実行時の安全ネット。

    backup()     — タスク開始前にコミット（/undo のベースライン）
    checkpoint() — ファイル書き込み後に自動コミット（細粒度ロールバック）
    rollback()   — 直前のチェックポイント（またはバックアップ）に戻す
    diff()       — バックアップ以降の差分統計を表示
    """

    def __init__(self):
        self._last_backup_hash: Optional[str] = None
        self._checkpoints: list[str] = []  # checkpoint コミットハッシュのスタック

    def _run_git(self, cmd: list[str], cwd: str) -> tuple[int, str, str]:
        import subprocess
        try:
            result = subprocess.run(
                ["git"] + cmd,
                cwd=cwd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except FileNotFoundError:
            return -1, "", "git が見つかりません（Git未インストール）"
        except Exception as e:
            return -1, "", str(e)

    def _is_git_repo(self, cwd: str) -> bool:
        rc, _, _ = self._run_git(["rev-parse", "--git-dir"], cwd)
        return rc == 0

    def _has_changes(self, cwd: str) -> bool:
        rc, out, _ = self._run_git(["status", "--porcelain"], cwd)
        return rc == 0 and bool(out.strip())

    def _get_head(self, cwd: str) -> Optional[str]:
        rc, out, _ = self._run_git(["rev-parse", "HEAD"], cwd)
        return out if rc == 0 else None

    def _ensure_git_user(self, cwd: str):
        """git user が未設定ならローカルに設定する"""
        rc, out, _ = self._run_git(["config", "user.email"], cwd)
        if rc != 0 or not out:
            self._run_git(["config", "user.email", "agent@unimog"], cwd)
            self._run_git(["config", "user.name",  "unimog-agent"], cwd)

    def backup(self, cwd: str) -> str:
        """タスク開始前のバックアップコミットを作成する"""
        if not self._is_git_repo(cwd):
            rc, _, err = self._run_git(["init"], cwd)
            if rc != 0:
                return f"git init 失敗: {err}"
            gitignore = Path(cwd) / ".gitignore"
            if not gitignore.exists():
                gitignore.write_text(
                    "__pycache__/\n*.pyc\n*.pyo\n*.log\n", encoding="utf-8"
                )
            print(C.gray(f"  [AutoGit] git init 完了: {cwd}"), flush=True)

        if not self._has_changes(cwd):
            self._last_backup_hash = self._get_head(cwd)
            return "変更なし。バックアップをスキップ。"

        self._ensure_git_user(cwd)
        self._run_git(["add", "."], cwd)
        rc, _, err = self._run_git(
            ["commit", "-m", "🤖 unimog-agent: backup before task"], cwd
        )
        if rc == 0:
            self._last_backup_hash = self._get_head(cwd)
            self._checkpoints = []  # 新タスク開始でスタックをリセット
            h = self._last_backup_hash
            return f"バックアップ完了: {h[:8] if h else '?'}"
        return f"バックアップ失敗: {err}"

    def checkpoint(self, cwd: str, tool: str, path: str = "") -> None:
        """ファイル書き込み後の自動チェックポイントコミット"""
        if not self._is_git_repo(cwd) or not self._has_changes(cwd):
            return
        self._ensure_git_user(cwd)
        file_name = Path(path).name if path else ""
        msg = f"🤖 checkpoint [{tool}]{' ' + file_name if file_name else ''}"
        self._run_git(["add", "."], cwd)
        rc, _, _ = self._run_git(["commit", "-m", msg], cwd)
        if rc == 0:
            h = self._get_head(cwd)
            if h:
                self._checkpoints.append(h)
                print(C.gray(f"  [AutoGit] ✓ {h[:8]} {msg}"), flush=True)

    def rollback(self, cwd: str) -> str:
        """直前のチェックポイント（またはバックアップ）にロールバックする"""
        if not self._is_git_repo(cwd):
            return "Gitリポジトリが見つかりません。"
        if self._checkpoints:
            self._checkpoints.pop()  # 最新チェックポイントを破棄
            target = self._checkpoints[-1] if self._checkpoints else self._last_backup_hash
        else:
            target = self._last_backup_hash
        cmd = ["reset", "--hard", target] if target else ["reset", "--hard", "HEAD~1"]
        rc, _, err = self._run_git(cmd, cwd)
        if rc == 0:
            h = self._get_head(cwd)
            return f"ロールバック完了: {h[:8] if h else '?'} へ戻しました"
        return f"ロールバック失敗: {err}"

    def diff(self, cwd: str) -> str:
        """バックアップ以降の差分統計を返す"""
        if not self._is_git_repo(cwd):
            return "Gitリポジトリが見つかりません。"
        if not self._last_backup_hash:
            return "バックアップが見つかりません（タスクを実行してください）。"
        rc, out, err = self._run_git(
            ["diff", self._last_backup_hash, "HEAD", "--stat"], cwd
        )
        return out if rc == 0 else f"diff 取得失敗: {err}"


# ──────────────────────────────────────────────
# ReactLog（ReActステップログ）
# ──────────────────────────────────────────────

class ReactLog:
    """ReActループの Thought / Action / Observation を蓄積・表示・エクスポートする"""

    def __init__(self):
        self.entries: list[dict] = []
        self.session_start: datetime = datetime.now()
        # 定期エクスポート用（None = 無効）
        self._auto_export_path: Optional[str] = None
        self._auto_export_interval: int = 0    # 秒
        self._auto_export_timer: Optional[threading.Timer] = None
        self._auto_export_lock = threading.Lock()

    # ── 定期エクスポート制御 ──────────────────────────────────────

    def start_auto_export(self, path: str, interval_sec: int):
        """定期エクスポートを開始する。既に動いていれば再スケジュール。"""
        self.stop_auto_export()
        with self._auto_export_lock:
            self._auto_export_path     = path
            self._auto_export_interval = interval_sec
        self._schedule_next()
        log.info({"event": "auto_export_start",
                  "path": path, "interval_sec": interval_sec})

    def stop_auto_export(self):
        """定期エクスポートを停止する。"""
        with self._auto_export_lock:
            if self._auto_export_timer:
                self._auto_export_timer.cancel()
                self._auto_export_timer = None

    def _schedule_next(self):
        """次回タイマーをセットする（内部用）。"""
        with self._auto_export_lock:
            if not self._auto_export_path or self._auto_export_interval <= 0:
                return
            t = threading.Timer(
                self._auto_export_interval, self._fire_export
            )
            t.daemon = True   # プロセス終了時に自動停止
            t.start()
            self._auto_export_timer = t

    def _fire_export(self):
        """タイマーコールバック: エクスポートして次回をスケジュール。"""
        try:
            path = self._auto_export_path
            if path:
                self.export_markdown(path)
                print(
                    C.gray(f"\n  [AutoExport] {Path(path).name} に保存しました "
                           f"({len(self.entries)} エントリ)"),
                    flush=True
                )
        except Exception as e:
            log.warning({"event": "auto_export_error", "error": str(e)})
        self._schedule_next()   # 次回をスケジュール

    @property
    def auto_export_enabled(self) -> bool:
        return bool(self._auto_export_path and self._auto_export_interval > 0)

    def clear(self):
        self.stop_auto_export()
        self.entries = []
        self.session_start = datetime.now()
        self._auto_export_path     = None
        self._auto_export_interval = 0

    def add(self, type_: str, **kwargs):
        self.entries.append({
            "type": type_,
            "ts": datetime.now().isoformat(timespec="seconds"),
            **kwargs,
        })

    def display(self):
        if not self.entries:
            print(C.gray("  (ログなし)"))
            return
        print(f"\n{C.green_dim('─' * 52)}")
        print(C.bold_green("  ReAct Log  ") + C.gray(f"({len(self.entries)} エントリ)"))
        print(C.green_dim("─" * 52))
        for e in self.entries:
            t    = e.get("type", "?")
            step = e.get("step", "?")
            if t == "thought":
                print(f"  {C.purple('💭')} [{step}] {C.purple(e.get('content', ''))}")
            elif t == "action":
                args_str = ", ".join(
                    f"{k}={repr(v)[:30]}" for k, v in e.get("args", {}).items()
                )
                print(f"  {C.bold_green('⚙')}  [{step}] {C.green(e.get('tool', '?'))}{C.cyan(f'({args_str})')}")
            elif t == "observation":
                obs = e.get("result", "")[:150].replace("\n", " ")
                print(f"  {C.cyan('👁')}  [{step}] → {C.cyan(obs)}")
        print(C.green_dim("─" * 52) + "\n")

    def export_markdown(self, path: str) -> str:
        lines = [
            "# ReAct Session Log",
            "",
            f"**開始時刻**: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**エントリ数**: {len(self.entries)}",
            "",
            "---",
            "",
        ]
        current_step = -1
        for e in self.entries:
            t    = e.get("type", "?")
            step = e.get("step", 0)
            ts   = e.get("ts", "")
            if step != current_step:
                current_step = step
                lines += [f"## Step {step}", ""]
            if t == "thought":
                lines += [f"### 💭 Thought `{ts}`", "", e.get("content", ""), ""]
            elif t == "action":
                tool = e.get("tool", "?")
                args = e.get("args", {})
                lines += [
                    f"### ⚙ Action: `{tool}` `{ts}`", "",
                    "```json",
                    json.dumps(args, ensure_ascii=False, indent=2),
                    "```", "",
                ]
            elif t == "observation":
                tool   = e.get("tool", "?")
                result = e.get("result", "")
                lines += [
                    f"### 👁 Observation: `{tool}` `{ts}`", "",
                    "```",
                    result[:2000],
                    "```", "",
                ]
        content = "\n".join(lines)
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(content, encoding="utf-8")
        return f"エクスポート完了: {path}  ({len(self.entries)} エントリ)"


GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

class GeminiAPIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(f"HTTP {status}: {message}")

class RateLimitError(GeminiAPIError):
    pass

class ServerError(GeminiAPIError):
    pass


def _to_gemini_contents(messages: list[dict]) -> list[dict]:
    """
    内部メッセージ形式を Gemini API の contents 形式に変換する。

    内部形式:
      {"role": "user",      "content": "text"}
      {"role": "assistant", "content": "thought", "function_calls": [{"name":..,"args":..}]}
      {"role": "user",      "content": "",        "function_results": [{"name":..,"result":..}]}

    Gemini API 形式:
      {"role": "user",  "parts": [{"text": "..."}]}
      {"role": "model", "parts": [{"text": "..."}, {"functionCall": {...}}]}
      {"role": "user",  "parts": [{"functionResponse": {"name":..,"response":{"result":..}}}]}
    """
    contents = []
    for m in messages:
        role = m.get("role", "user")
        gemini_role = "user" if role == "user" else "model"

        if m.get("function_results"):
            # functionResponse メッセージ（ツール結果）
            parts = [
                {
                    "functionResponse": {
                        "name": r["name"],
                        "response": {"result": r["result"]}
                    }
                }
                for r in m["function_results"]
            ]
            contents.append({"role": "user", "parts": parts})

        elif m.get("function_calls") and role == "assistant":
            # functionCall を含むモデルの応答
            parts: list[dict] = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            parts += [
                {"functionCall": {"name": fc["name"], "args": fc.get("args", {})}}
                for fc in m["function_calls"]
            ]
            contents.append({"role": "model", "parts": parts})

        else:
            content_text = str(m.get("content", ""))
            if content_text:
                contents.append({"role": gemini_role, "parts": [{"text": content_text}]})

    return contents


def _msg_char_count(m: dict) -> int:
    """メッセージの文字数を返す（function_results も含む）"""
    count = len(str(m.get("content", "")))
    for r in m.get("function_results", []):
        count += len(str(r.get("result", "")))
    for fc in m.get("function_calls", []):
        count += len(str(fc.get("args", "")))
    return count


def _fmt_msg_for_summary(m: dict) -> str:
    """要約用にメッセージを1行テキストに変換する"""
    role = m.get("role", "?")
    if m.get("function_results"):
        results = "; ".join(
            f"{r['name']}: {str(r.get('result',''))[:200]}"
            for r in m["function_results"]
        )
        return f"[{role}/tool_result]: {results}"
    if m.get("function_calls"):
        calls = ", ".join(fc["name"] for fc in m["function_calls"])
        return f"[{role}]: {str(m.get('content',''))[:200]} [calls: {calls}]"
    return f"[{role}]: {str(m.get('content', ''))[:500]}"


def _trim_messages_smart(messages: list[dict]) -> list[dict]:
    """
    ペイロード削減のためにメッセージを賢くトリムする。

    優先削除順（重要度が低いものから）:
      1. ツール結果メッセージ（function_results または [ツール: で始まるもの）の古い順
      2. それでも足りなければ古い順に均等削除（先頭2件は保護）

    1回の呼び出しで約25%削減を目標とする。
    """
    protected = messages[:2]
    body = messages[2:]

    if not body:
        return messages

    target_remove = max(2, len(body) // 4)

    # ① ツール結果メッセージを古い順に探して削除候補とする
    tool_indices = [
        i for i, m in enumerate(body)
        if m.get("role") == "user" and (
            bool(m.get("function_results")) or
            str(m.get("content", "")).startswith("[ツール:")
        )
    ]

    removed = 0
    indices_to_remove: set[int] = set()

    for idx in tool_indices:
        if removed >= target_remove:
            break
        indices_to_remove.add(idx)
        removed += 1

    # ② ツール結果だけでは足りない場合は古い順に追加削除
    if removed < target_remove:
        for i in range(len(body)):
            if removed >= target_remove:
                break
            if i not in indices_to_remove:
                indices_to_remove.add(i)
                removed += 1

    trimmed_body = [m for i, m in enumerate(body) if i not in indices_to_remove]
    return protected + trimmed_body


def _call_gemini_api(account: AccountConfig, messages: list[dict],
                     tool_specs: list[dict],
                     system_prompt: Optional[str] = None) -> dict:
    """Gemini API を直接呼び出す（urllib のみ使用）"""
    url = f"{GEMINI_API_BASE}/{account.model}:generateContent?key={account.api_key}"

    # Gemini 形式への変換（functionCall / functionResponse 正式フォーマット対応）
    contents = _to_gemini_contents(messages)

    # Gemma 4 は thinkingBudget 非対応。thinking は system prompt の <|think|> トークンで制御。
    # Gemini 2.5 系は thinkingBudget 対応。モデル名で自動判別。
    is_gemini_thinking_supported = (
        "gemini-2.5" in account.model or
        "gemini-3" in account.model
    )
    payload: dict[str, Any] = {"contents": contents}

    # system_instruction として正式に送信（会話メッセージと明確に分離）
    if system_prompt:
        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
    if is_gemini_thinking_supported:
        thinking_budget_map = {"HIGH": -1, "MEDIUM": 8192, "LOW": 1024, "NONE": 0}
        thinking_budget = thinking_budget_map.get(account.thinking_level.upper(), -1)
        if thinking_budget != 0:
            payload["generationConfig"] = {
                "thinkingConfig": {"thinkingBudget": thinking_budget}
            }

    if tool_specs:
        payload["tools"] = [{
            "functionDeclarations": tool_specs
        }]
        payload["toolConfig"] = {
            "functionCallingConfig": {"mode": "AUTO"}
        }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(body_text)
            msg = err_json.get("error", {}).get("message", body_text)
        except Exception:
            msg = body_text
        if e.code == 429:
            raise RateLimitError(e.code, msg)
        if e.code >= 500:
            raise ServerError(e.code, msg)
        raise GeminiAPIError(e.code, msg)
    except urllib.error.URLError as e:
        raise GeminiAPIError(0, f"ネットワークエラー: {e.reason}")


def _stream_gemini_api(account: AccountConfig, messages: list[dict],
                       tool_specs: list[dict],
                       system_prompt: Optional[str] = None):
    """
    streamGenerateContent SSE エンドポイントでストリーミング呼び出し。

    yields (text_chunk: str, tool_calls: list[dict], finish_reason: str)
      text_chunk   : テキストのかたまり（空文字の場合あり）
      tool_calls   : functionCall が含まれるチャンクのみ非空リスト
      finish_reason: 最終チャンクでのみ非空文字列
    """
    url = (f"{GEMINI_API_BASE}/{account.model}"
           f":streamGenerateContent?alt=sse&key={account.api_key}")

    # ─ payload（_call_gemini_api と同じ構成）─
    # functionCall / functionResponse 正式フォーマット対応
    contents = _to_gemini_contents(messages)

    is_gemini_thinking_supported = (
        "gemini-2.5" in account.model or "gemini-3" in account.model
    )
    payload: dict[str, Any] = {"contents": contents}

    if system_prompt:
        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}
    if is_gemini_thinking_supported:
        thinking_budget_map = {"HIGH": -1, "MEDIUM": 8192, "LOW": 1024, "NONE": 0}
        thinking_budget = thinking_budget_map.get(account.thinking_level.upper(), -1)
        if thinking_budget != 0:
            payload["generationConfig"] = {
                "thinkingConfig": {"thinkingBudget": thinking_budget}
            }
    if tool_specs:
        payload["tools"] = [{"functionDeclarations": tool_specs}]
        payload["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req  = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
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

                candidates = chunk.get("candidates", [])
                if not candidates:
                    continue
                candidate     = candidates[0]
                parts         = candidate.get("content", {}).get("parts", [])
                finish_reason = candidate.get("finishReason", "")

                text_chunk = ""
                chunk_tools: list[dict] = []
                for part in parts:
                    if "text" in part:
                        text_chunk += part["text"]
                    elif "functionCall" in part:
                        fc = part["functionCall"]
                        chunk_tools.append({"name": fc["name"],
                                            "args": fc.get("args", {})})

                yield text_chunk, chunk_tools, finish_reason

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
        raise GeminiAPIError(e.code, msg)
    except urllib.error.URLError as e:
        raise GeminiAPIError(0, f"ネットワークエラー: {e.reason}")


# ──────────────────────────────────────────────
# アカウントローテーター
# ──────────────────────────────────────────────

class AccountRotator:
    """
    3アカウントを Token Bucket で管理し、最適なアカウントを選択。

    選択戦略（優先順）:
      1. すぐ使えるアカウント（トークンあり + RPD残あり）→ RPD残量最大を優先
      2. 少し待てば使えるアカウント（RPM待ち最短）
      3. 全アカウント RPD 枯渇 → RuntimeError

    Token Bucket の恩恵:
      - acquire() が O(1) で wait 秒数を返すのでロック競合を最小化
      - 補充が連続的なので「ウィンドウ境界でバーストが2倍」問題が起きない
      - 429受信時は外部バックオフ後に再 acquire → 自然にレート調整
    """

    def __init__(self, accounts: list[AccountConfig]):
        self.accounts = accounts
        self._lock = threading.Lock()

    def pick(self) -> tuple[AccountConfig, float]:
        """
        最適なアカウントを選んで (account, wait_sec) を返す。

        ローテーション戦略（均等分散）:
          1. wait_time() でトークン消費せずに状態を確認
          2. 即利用可能なアカウントから RPD残量が均等になるよう選択
          3. 全アカウント RPM 待ちなら待ち時間最短を選択
          4. acquire() は選んだ1アカウントのみに実行（多重消費なし）
        """
        with self._lock:
            ready: list[AccountConfig] = []
            waiting: list[tuple[AccountConfig, float]] = []

            for acc in self.accounts:
                # wait_time() はトークンを消費しない（参照のみ）
                if acc.bucket.rpd_remaining == 0 and not acc.bucket.rpd_unlimited:
                    continue  # RPD 枯渇: スキップ
                wait = acc.bucket.wait_time()
                if wait == 0.0:
                    ready.append(acc)
                else:
                    waiting.append((acc, wait))

            if ready:
                # RPD 無制限アカウントは使用回数で均等化、有制限はRPD残量で均等化
                ready.sort(key=lambda a: (
                    a.bucket._rpd_count if a.bucket.rpd_unlimited
                    else -a.bucket.rpd_remaining
                ))
                selected = ready[0]
                # 選んだアカウントのみ acquire
                ok, wait = selected.bucket.acquire()
                if ok:
                    return selected, 0.0
                # ごく稀にトークンが枯渇した場合は待ちとして返す
                return selected, wait

            if waiting:
                waiting.sort(key=lambda x: x[1])
                return waiting[0]

            raise RuntimeError(
                "全アカウントが本日の RPD 上限に達しました。明日 UTC 00:00 にリセットされます。"
            )

    def record(self, account: AccountConfig):
        """waiting から選ばれたアカウントの acquire（wait 後に呼ぶ）"""
        account.bucket.acquire()

    # ── Plan-and-Execute サポート ──────────────────────────────

    def total_tokens(self) -> float:
        """全アカウントの利用可能トークン合計（消費ゼロ・参照のみ）"""
        return sum(acc.bucket.tokens_available for acc in self.accounts)

    def can_afford_reviewer(self) -> bool:
        """
        Reviewer を呼べるか判定（消費ゼロ）。
        RPD 無制限モード（GEMINI_RPD=0）では常に True を返す。
        有制限モードでは RPM トークン残量 >= 2.0 を条件とする。
        """
        if all(acc.bucket.rpd_unlimited for acc in self.accounts):
            return True  # RPD無制限: Reviewer/Reflector を常時有効化
        return self.total_tokens() >= 2.0

    def wait_to_start(self, step_count: int) -> float:
        """
        タスク開始に必要な待ち時間を秒で返す。
        必要コール数 = Planner×1 + Executor×steps（最低限の見積もり）
        """
        needed = float(1 + step_count)
        available = self.total_tokens()
        if available >= needed:
            return 0.0
        total_refill = sum(acc.bucket._refill_rate for acc in self.accounts)
        if total_refill <= 0:
            return 0.0
        return (needed - available) / total_refill

    def status(self) -> list[dict]:
        return [
            {
                "name": acc.name,
                "model": acc.model,
                "rpd_remaining": acc.bucket.rpd_remaining,
                "rpd_unlimited": acc.bucket.rpd_unlimited,
                "tokens_available": round(acc.bucket.tokens_available, 2),
                "rpm_limit": acc.bucket.rpm_limit,
            }
            for acc in self.accounts
        ]

# ──────────────────────────────────────────────
# エージェント本体
# ──────────────────────────────────────────────

MAX_RETRIES = 5
BASE_BACKOFF = 2.0       # 秒
MAX_BACKOFF = 120.0      # 秒
MAX_TOOL_ROUNDS = 50     # 1ターンあたりのツール呼び出し上限（RPD無制限のため拡大）
TOOL_OUTPUT_LIMIT = 20000  # ツール出力の文字数上限（4000→20000: ファイル全体を読める）

# キャッシュ対象の読み取り系ツール（同一引数で同じ結果が返るもの）
_CACHEABLE_TOOLS = frozenset({"read_file", "list_directory", "glob", "search_files", "fetch_webpage"})


def _print_write_diff(fn_name: str, fn_args: dict) -> None:
    """
    edit_file / write_file 実行前に変更差分を端末に表示する。
    plan モードでは情報表示のみ（承認なし）。
    react モードの承認フローは InteractiveOrchestrator._confirm_write_tool が担う。
    """
    if fn_name == "edit_file":
        path      = fn_args.get("path", "?")
        old_str   = fn_args.get("old_string", "")
        new_str   = fn_args.get("new_string", "")
        old_lines = old_str.splitlines(keepends=True)
        new_lines = new_str.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
        ))
        if not diff:
            return
        print(C.gray(f"  [diff] {path}"), flush=True)
        for line in diff:
            if line.startswith("+++") or line.startswith("---"):
                print(C.gray(f"    {line}"), end="", flush=True)
            elif line.startswith("+"):
                print(C.green(f"    {line}"), end="", flush=True)
            elif line.startswith("-"):
                print(C.red(f"    {line}"), end="", flush=True)
            else:
                print(C.dim(f"    {line}"), end="", flush=True)
        print(flush=True)

    elif fn_name == "write_file":
        path    = fn_args.get("path", "?")
        content = fn_args.get("content", "")
        p = Path(path)
        if p.exists():
            old_lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            new_lines = content.splitlines(keepends=True)
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""
            ))
            if not diff:
                return
            print(C.gray(f"  [diff] {path}"), flush=True)
            for line in diff:
                if line.startswith("+++") or line.startswith("---"):
                    print(C.gray(f"    {line}"), end="", flush=True)
                elif line.startswith("+"):
                    print(C.green(f"    {line}"), end="", flush=True)
                elif line.startswith("-"):
                    print(C.red(f"    {line}"), end="", flush=True)
                else:
                    print(C.dim(f"    {line}"), end="", flush=True)
            print(flush=True)
        else:
            lines = content.splitlines()
            preview = "\n".join(f"    {C.green('+ ' + l)}" for l in lines[:20])
            suffix  = C.gray(f"\n    ... (+{len(lines) - 20}行)") if len(lines) > 20 else ""
            print(C.gray(f"  [新規ファイル] {path}") + f"\n{preview}{suffix}", flush=True)


class GeminiAgent:
    """
    claw-code スタイルの エージェントループ:
      user → [API call] → tool calls → [API call] → ... → final answer
    """

    # セッション圧縮: 会話の総文字数がこの値を超えたら AI 要約で圧縮
    # メッセージ数ではなくバイト数ベースで判定（大きいツール出力を確実に捕捉）
    COMPACTION_THRESHOLD_CHARS = 500_000  # 50万文字 ≈ 約125kトークン相当
    # 要約後に保持する直近メッセージ数（以前: 8 → 現在: 20 = 10往復）
    COMPACTION_KEEP_RECENT = 20

    def __init__(self, rotator: AccountRotator, tool_registry: ToolRegistry):
        self.rotator = rotator
        self.tools = tool_registry
        self.conversation: list[dict] = []
        self.system_prompt: Optional[str] = None
        self.thinking_enabled: bool = True   # /think on|off で切替
        self.cwd: str = str(Path.cwd())      # カレントフォルダ追跡
        self._task_goal: Optional[str] = None  # 現在のタスクゴール
        self._tool_cache: dict[str, str] = {}  # 読み取り系ツールのセッション内キャッシュ

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def set_thinking(self, enabled: bool, silent: bool = False):
        self.thinking_enabled = enabled
        if not silent:
            state = "ON" if enabled else "OFF"
            print(f"  推論モード: {state}")

    # ────────────────────────────────────────────
    # カレントフォルダ認識（1行のみ・毎回スキャンしない）
    # ────────────────────────────────────────────
    def _build_context_header(self) -> str:
        return f"[作業フォルダ] {self.cwd}"

    def set_cwd(self, path: str):
        self.cwd = path
        print(f"  作業フォルダを変更: {path}")

    # ────────────────────────────────────────────
    # ② タスク管理
    # ────────────────────────────────────────────
    def start_task(self, goal: str):
        """複数ステップにまたがるタスクを開始"""
        self._task_goal = goal
        log.info({"event": "task_start", "goal": goal[:80]})

    def end_task(self):
        self._task_goal = None

    def _task_context(self) -> str:
        """タスク進行中の場合、ゴールをコンテキストに注入"""
        if not self._task_goal:
            return ""
        return f"[現在のタスク] {self._task_goal}"

    # ────────────────────────────────────────────
    # ③ セッション圧縮
    # ────────────────────────────────────────────
    def _generate_summary(self, messages_to_summarize: list[dict]) -> str:
        """
        指定した会話メッセージを AI で要約する（セッション記憶の圧縮に使用）。
        ツールなし・thinking OFF で高速実行。RPD 無制限なので積極的に呼ぶ。
        """
        history_text = "\n".join(
            _fmt_msg_for_summary(m) for m in messages_to_summarize
        )
        summary_messages = [
            {
                "role": "user",
                "content": (
                    "以下の会話履歴を要約してください。\n"
                    "重要な情報（ファイル名・コマンド結果・決定事項・エラー内容・変数値）を"
                    "箇条書きで保持し、不要な繰り返しや挨拶は省略してください:\n\n"
                    + history_text
                )
            }
        ]
        # thinking OFF で実行（高速・RPM トークン節約）
        prev_thinking = self.thinking_enabled
        self.thinking_enabled = False
        try:
            response = self._api_call_with_retry(summary_messages, override_tool_specs=[])
            return self._extract_text(response) or "(要約失敗)"
        except Exception as e:
            log.warning({"event": "summary_failed", "error": str(e)})
            return f"(会話 {len(messages_to_summarize)} 件を省略: {type(e).__name__})"
        finally:
            self.thinking_enabled = prev_thinking

    def _compact_if_needed(self):
        """
        会話の総文字数が COMPACTION_THRESHOLD_CHARS を超えたら AI 要約で圧縮する。
        メッセージ数ではなく実際のサイズで判定するため、大きいツール出力も確実に捕捉。

        保護ルール:
          - conversation[0:2] (最初の指示と応答) は常に保持
          - 要約対象部分を AI が要約 → summary_msg として挿入
          - 直近 COMPACTION_KEEP_RECENT 件はそのまま保持
        """
        total_chars = sum(_msg_char_count(m) for m in self.conversation)
        if total_chars <= self.COMPACTION_THRESHOLD_CHARS:
            return

        keep_recent = self.COMPACTION_KEEP_RECENT
        first_pair = self.conversation[:2]
        boundary = len(self.conversation) - keep_recent
        to_summarize = self.conversation[2:boundary]
        recent_part = self.conversation[boundary:]

        if not to_summarize:
            return

        print(C.gray(f"  [会話要約圧縮中... {len(to_summarize)}件 / {total_chars:,}文字を要約します]"), flush=True)
        summary_text = self._generate_summary(to_summarize)

        summary_msg = {
            "role": "user",
            "content": f"[以前の会話の要約（重要な情報を保持）]\n{summary_text}"
        }
        summary_ack = {
            "role": "assistant",
            "content": "会話の要約を確認しました。この文脈を踏まえて引き続き対応します。"
        }

        self.conversation = first_pair + [summary_msg, summary_ack] + recent_part
        after_chars = sum(_msg_char_count(m) for m in self.conversation)
        log.info({"event": "compaction_summary",
                  "summarized": len(to_summarize), "kept": len(self.conversation),
                  "before_chars": total_chars, "after_chars": after_chars})
        print(C.gray(f"  [要約完了: {len(to_summarize)}件 → 要約に変換、直近{keep_recent}件保持 ({total_chars:,}→{after_chars:,}文字)]"))

    def _api_call_with_retry(self, messages: list[dict],
                             override_tool_specs: Optional[list] = None) -> dict:
        """
        Token Bucket 対応リトライループ。

        pick() が ready アカウントを返した場合 → acquire 済みなので record() 不要
        pick() が waiting アカウントを返した場合 → wait 後に record() で acquire
        429/503 受信 → 指数バックオフ後に次の pick() でローテーション

        override_tool_specs: Noneなら self.tools.get_specs() を使用。
                             []を渡すとツールなしモード（要約・検証用）。
        """
        tool_specs = override_tool_specs if override_tool_specs is not None else self.tools.get_specs()
        attempt = 0
        # 500エラー時にペイロードを削って再リトライするための作業コピー
        working_messages = list(messages)

        # 推論モードをアカウント設定に一時反映
        effective_thinking = "HIGH" if self.thinking_enabled else "NONE"
        for acc in self.rotator.accounts:
            acc.thinking_level = effective_thinking

        while attempt < MAX_RETRIES:
            account, wait = self.rotator.pick()

            if wait > 0:
                jitter = random.uniform(0.05, 0.3)
                actual_wait = wait + jitter
                log.info({"event": "rpm_wait", "account": account.name,
                          "wait_sec": round(actual_wait, 2)})
                print(C.yellow(f"  ⏳ RPM待機中 {actual_wait:.1f}秒 ({account.name})"), flush=True)
                time.sleep(actual_wait)
                self.rotator.record(account)

            try:
                tokens = round(account.bucket.tokens_available, 1)
                print(C.gray(f"  → {account.name}  残トークン:{tokens}/{account.bucket.rpm_limit}"), flush=True)
                log.info({"event": "api_call", "account": account.name,
                          "attempt": attempt + 1,
                          "tokens": tokens,
                          "rpd_left": account.bucket.rpd_remaining,
                          "msg_count": len(working_messages)})
                response = _call_gemini_api(account, working_messages, tool_specs,
                                            system_prompt=self.system_prompt)
                log.info({"event": "api_ok", "account": account.name})
                return response

            except RateLimitError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1),
                              MAX_BACKOFF)
                log.warning({"event": "rate_limit_429", "account": account.name,
                             "backoff_sec": round(backoff, 1)})
                print(C.yellow(f"  ⚠ 429 レート制限 → {backoff:.0f}秒待機してリトライ"), flush=True)
                time.sleep(backoff)
                attempt += 1

            except ServerError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2),
                              MAX_BACKOFF)
                log.warning({"event": "server_error", "account": account.name,
                             "backoff_sec": round(backoff, 1)})
                # 500は初回から古いメッセージを削ってペイロードを縮小して再試行
                # working_messages[0:2] はシステムプロンプト部分なので保護
                if len(working_messages) > 6:
                    working_messages = _trim_messages_smart(working_messages)
                    print(C.yellow(
                        f"  ⚠ サーバーエラー({e.status}) → ペイロード削減(残{len(working_messages)}件) + {backoff:.0f}秒待機"
                    ), flush=True)
                    log.warning({"event": "payload_trimmed",
                                 "remaining": len(working_messages)})
                else:
                    print(C.yellow(f"  ⚠ サーバーエラー({e.status}) → {backoff:.0f}秒待機"), flush=True)
                time.sleep(backoff)
                attempt += 1

            except GeminiAPIError as e:
                log.error({"event": "api_error", "account": account.name,
                           "status": e.status, "msg": e.message})
                print(C.red(f"  ✗ APIエラー({e.status}): {e.message}"), flush=True)
                raise

            except (http.client.RemoteDisconnected,
                    ConnectionResetError, ConnectionError, TimeoutError) as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2),
                              MAX_BACKOFF)
                log.warning({"event": "connection_error", "error": str(e),
                             "backoff_sec": round(backoff, 1)})
                print(C.yellow(f"  ⚠ 接続エラー → {backoff:.0f}秒待機してリトライ ({type(e).__name__})"), flush=True)
                time.sleep(backoff)
                attempt += 1

        raise RuntimeError(f"API呼び出し最大リトライ数 ({MAX_RETRIES}) を超えました")

    def _stream_react_call(self, messages: list, callback=None) -> tuple[str, list]:
        """
        ストリーミング API 呼び出し。
        テキストチャンクを callback 経由で送信し、(full_text, tool_calls) を返す。
        """
        tool_specs = self.tools.get_specs()
        effective_thinking = "HIGH" if self.thinking_enabled else "NONE"
        for acc in self.rotator.accounts:
            acc.thinking_level = effective_thinking

        attempt = 0
        working_messages = list(messages)

        while attempt < MAX_RETRIES:
            account, wait = self.rotator.pick()

            if wait > 0:
                jitter      = random.uniform(0.05, 0.3)
                actual_wait = wait + jitter
                log.info({"event": "rpm_wait", "account": account.name,
                          "wait_sec": round(actual_wait, 2)})
                print(C.yellow(f"  ⏳ RPM待機中 {actual_wait:.1f}秒 ({account.name})"),
                      flush=True)
                time.sleep(actual_wait)
                self.rotator.record(account)

            try:
                tokens = round(account.bucket.tokens_available, 1)
                print(C.gray(
                    f"  → {account.name}  残トークン:{tokens}/{account.bucket.rpm_limit}"
                ), flush=True)
                log.info({"event": "api_call_stream", "account": account.name,
                          "attempt": attempt + 1, "tokens": tokens,
                          "msg_count": len(working_messages)})

                full_text:  str       = ""
                tool_calls_list: list[dict] = []
                header_sent         = False

                try:
                    for text_chunk, chunk_tools, _ in _stream_gemini_api(
                        account, working_messages, tool_specs, self.system_prompt
                    ):
                        if text_chunk:
                            if callback:
                                if not header_sent:
                                    callback(f"\n  {C.purple('💭')} ")
                                    header_sent = True
                                callback(C.purple(text_chunk))
                            full_text += text_chunk
                        for ct in chunk_tools:
                            name = ct.get("name")
                            args = ct.get("args", {})
                            if name:
                                tool_calls_list.append({"name": name, "args": dict(args)})
                            elif tool_calls_list:
                                tool_calls_list[-1]["args"].update(args)

                except KeyboardInterrupt:
                    print(C.yellow("\n\n  [割り込み] Ctrl+C — ストリームを停止しました。"),
                          flush=True)
                    return "__interrupted__", []

                if header_sent and callback:
                    callback("\n")

                tool_calls = tool_calls_list
                log.info({"event": "api_ok_stream", "account": account.name,
                          "text_len": len(full_text),
                          "tool_calls": len(tool_calls)})
                return full_text, tool_calls

            except RateLimitError:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1),
                              MAX_BACKOFF)
                log.warning({"event": "rate_limit_429", "account": account.name,
                             "backoff_sec": round(backoff, 1)})
                print(C.yellow(f"  ⚠ 429 レート制限 → {backoff:.0f}秒待機してリトライ"),
                      flush=True)
                time.sleep(backoff)
                attempt += 1

            except ServerError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2),
                              MAX_BACKOFF)
                if len(working_messages) > 6:
                    working_messages = _trim_messages_smart(working_messages)
                    print(C.yellow(
                        f"  ⚠ サーバーエラー({e.status}) → ペイロード削減"
                        f"(残{len(working_messages)}件) + {backoff:.0f}秒待機"
                    ), flush=True)
                else:
                    print(C.yellow(
                        f"  ⚠ サーバーエラー({e.status}) → {backoff:.0f}秒待機"
                    ), flush=True)
                time.sleep(backoff)
                attempt += 1

            except GeminiAPIError as e:
                log.error({"event": "api_error", "account": account.name,
                           "status": e.status, "msg": e.message})
                print(C.red(f"  ✗ APIエラー({e.status}): {e.message}"), flush=True)
                raise

            except (http.client.RemoteDisconnected,
                    ConnectionResetError, ConnectionError, TimeoutError) as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2),
                              MAX_BACKOFF)
                log.warning({"event": "connection_error", "error": str(e),
                             "backoff_sec": round(backoff, 1)})
                print(C.yellow(
                    f"  ⚠ 接続エラー → {backoff:.0f}秒待機してリトライ ({type(e).__name__})"
                ), flush=True)
                time.sleep(backoff)
                attempt += 1

        raise RuntimeError(
            f"ストリーミング API 最大リトライ数 ({MAX_RETRIES}) を超えました"
        )

    def _extract_text(self, response: dict) -> Optional[str]:
        try:
            parts = response["candidates"][0]["content"]["parts"]
            texts = [p["text"] for p in parts if "text" in p]
            return "\n".join(texts) if texts else None
        except (KeyError, IndexError):
            return None

    def _extract_tool_calls(self, response: dict) -> list[dict]:
        try:
            parts = response["candidates"][0]["content"]["parts"]
            return [p["functionCall"] for p in parts if "functionCall" in p]
        except (KeyError, IndexError):
            return []

    def _finish_reason(self, response: dict) -> str:
        try:
            return response["candidates"][0].get("finishReason", "UNKNOWN")
        except (KeyError, IndexError):
            return "UNKNOWN"

    def _summarize_if_long(self, tool_name: str, result_str: str) -> str:
        """
        TOOL_OUTPUT_LIMIT を超えたツール出力を軽量モデルで要約して返す。
        要約失敗時は先頭 TOOL_OUTPUT_LIMIT 文字にフォールバック。
        """
        if len(result_str) <= TOOL_OUTPUT_LIMIT:
            return result_str
        print(C.gray(
            f"  [要約] {tool_name} の出力が長いため要約します "
            f"({len(result_str):,}文字 → 上限{TOOL_OUTPUT_LIMIT:,}文字)..."
        ), flush=True)
        summary_messages = [{
            "role": "user",
            "content": (
                f"以下はツール「{tool_name}」の実行結果です。"
                f"重要な情報をすべて保持しつつ3000文字以内で要約してください。\n\n"
                f"{result_str[:50000]}"
            ),
        }]
        prev_thinking = self.thinking_enabled
        self.thinking_enabled = False
        try:
            response = self._api_call_with_retry(summary_messages, override_tool_specs=[])
            summary = self._extract_text(response)
            if not summary:
                raise ValueError("空の要約レスポンス")
            log.info({"event": "tool_summarized", "tool": tool_name,
                      "original": len(result_str), "summary": len(summary)})
            return summary
        except Exception as e:
            log.warning({"event": "summarize_failed", "tool": tool_name, "error": str(e)})
            print(C.yellow(f"  [要約失敗] 先頭{TOOL_OUTPUT_LIMIT:,}文字にフォールバック"), flush=True)
            return result_str[:TOOL_OUTPUT_LIMIT]
        finally:
            self.thinking_enabled = prev_thinking

    def _make_cache_key(self, fn_name: str, fn_args: dict) -> str:
        return f"{fn_name}:{json.dumps(fn_args, sort_keys=True, ensure_ascii=False)}"

    def _invalidate_cache_for_path(self, path: str):
        """ファイル書き込み後に該当パスの read_file・list_directory キャッシュを削除する。"""
        path_json  = json.dumps(path, ensure_ascii=False)
        parent_dir = str(Path(path).parent)
        dir_key    = self._make_cache_key("list_directory", {"path": parent_dir})
        for key in list(self._tool_cache):
            if key.startswith(f"read_file:") and path_json in key:
                self._tool_cache.pop(key, None)
            elif key == dir_key:
                self._tool_cache.pop(key, None)

    def _run_single_tool(self, tc: dict) -> tuple[str, str]:
        """
        1ツール呼び出しを実行して (fn_name, result_str) を返す。
        並列実行から呼ばれるためスレッドセーフ。
        キャッシュ対象ツールはセッション内で結果を再利用する。
        """
        fn_name = tc.get("name", "")
        fn_args = tc.get("args", {})
        args_preview = ", ".join(f"{k}={repr(v)[:40]}" for k, v in fn_args.items())
        print(C.bold_green(f"  ⚙ ") + C.green(fn_name) + C.cyan(f"({args_preview})"), flush=True)

        # ── キャッシュヒット確認（読み取り系のみ）────────────────
        if fn_name in _CACHEABLE_TOOLS:
            cache_key = self._make_cache_key(fn_name, fn_args)
            if cache_key in self._tool_cache:
                cached = self._tool_cache[cache_key]
                print(C.gray(f"    [キャッシュ] {len(cached)}文字 (再取得スキップ)"), flush=True)
                return fn_name, cached

        # ── Plan モードのdiff表示（write_file / edit_file）────────
        _print_write_diff(fn_name, fn_args)

        try:
            result = self.tools.execute(fn_name, fn_args)
            result_str = self._summarize_if_long(fn_name, str(result))
        except Exception as e:
            result_str = f"ツール実行エラー: {fn_name}: {e}"
            log.error({"event": "tool_error", "tool": fn_name, "error": str(e)})
            print(C.red(f"    ✗ {e}"), flush=True)
            return fn_name, result_str

        # ── キャッシュ登録 / 書き込み後キャッシュ無効化 ──────────
        if fn_name in _CACHEABLE_TOOLS:
            self._tool_cache[cache_key] = result_str  # type: ignore[possibly-undefined]
        elif fn_name in ("write_file", "edit_file", "patch_file", "delete_file"):
            self._invalidate_cache_for_path(fn_args.get("path", ""))

        log.info({"event": "tool_result", "tool": fn_name, "result_len": len(result_str)})
        print(C.cyan(f"    → {len(result_str)}文字 取得"), flush=True)
        return fn_name, result_str

def run(self, user_message: str) -> str:
    """
    エージェントループのエントリポイント。
    user_message に対して最終応答を文字列で返す。
    """
    # 内部の run_stream を利用し、ストリーミングなしとして動作させる
    return self.run_stream(user_message, callback=None)

def run_stream(self, user_message: str, callback=None) -> str:
    """
    エージェントループのストリーミング版。
    AIの生成トークンを callback に逐次送信し、最終応答を文字列で返す。
    """
    # 必要に応じて会話を圧縮
    self._compact_if_needed()

    # コンテキストヘッダー（作業フォルダ・タスクゴール）をユーザーメッセージの先頭に付加
    context_header = self._build_context_header()
    task_ctx = self._task_context()
    prefix_parts = [p for p in [context_header, task_ctx] if p]
    if prefix_parts:
        augmented_message = "\n\n".join(prefix_parts) + "\n\n" + user_message
    else:
        augmented_message = user_message

    # 会話履歴を構築
    messages: list[dict] = []
    messages.extend(self.conversation)
    old_conv_len = len(self.conversation)
    messages.append({"role": "user", "content": augmented_message})

    tool_round = 0

    while tool_round < MAX_TOOL_ROUNDS:
        # ── ストリーミング生成 ─────────────────────────────────────
        # _stream_react_call を使用してトークンを callback に流し、結果を受け取る
        text, tool_calls = self._stream_react_call(messages, callback=callback)

        if text == "__interrupted__":
            return "ユーザーによって中断されました"

        log.info({"event": "response_stream", "has_text": text is not None,
                  "tool_calls": len(tool_calls)})

        # ── ツール呼び出しがある場合 ──
        if tool_calls:
            tool_round += 1
            if tool_round > MAX_TOOL_ROUNDS:
                log.warning({"event": "tool_limit_reached"})
                break

            # アシスタントの応答をメッセージ履歴に追加
            messages.append({
                "role": "assistant",
                "content": text or "",
                "function_calls": [
                    {"name": tc["name"], "args": tc.get("args", {})}
                    for tc in tool_calls
                ],
            })

            # ── ツール実行（複数なら並列）─────────────────────────
            if len(tool_calls) > 1:
                print(C.orange(f"  ⚡ {len(tool_calls)} ツールを並列実行"), flush=True)
                ordered: list[Optional[dict]] = [None] * len(tool_calls)
                with ThreadPoolExecutor(max_workers=len(tool_calls)) as tpool:
                    fmap = {
                        tpool.submit(self._run_single_tool, tc): i
                        for i, tc in enumerate(tool_calls)
                    }
                    for f in as_completed(fmap):
                        idx = fmap[f]
                        fn_name, result_str = f.result()
                        ordered[idx] = {
                            "tool": fn_name,
                            "result": result_str[:TOOL_OUTPUT_LIMIT],
                        }
                tool_results = ordered  # type: ignore
            else:
                fn_name, result_str = self._run_single_tool(tool_calls[0])
                tool_results = [{"tool": fn_name,
                                 "result": result_str[:TOOL_OUTPUT_LIMIT]}]

            # ツール結果をメッセージに追加
            messages.append({
                "role": "user",
                "content": "",
                "function_results": [
                    {"name": r["tool"], "result": r["result"]}
                    for r in tool_results
                ],
            })
            continue

        # ── 最終応答 ──
        final_text = text or "(応答なし)"

        # 会話履歴を更新
        self.conversation.append({"role": "user", "content": user_message})
        self.conversation.extend(messages[old_conv_len + 1:])
        self.conversation.append({"role": "assistant", "content": final_text})

        return final_text

    return "エラー: ツール呼び出しの上限に達しました"

    def clear_history(self):
        self.conversation = []
        self._tool_cache.clear()
        self.end_task()

    def print_status(self):
        status = self.rotator.status()
        print("\n=== アカウントステータス (Token Bucket) ===")
        for s in status:
            tokens = s["tokens_available"]
            rpm_limit = s["rpm_limit"]
            filled = int(tokens)
            bar = "█" * filled + "░" * (rpm_limit - filled)
            rpd_str = "無制限 ∞" if s["rpd_unlimited"] else f"{s['rpd_remaining']} remaining"
            print(f"  [{s['name']}] {s['model']}")
            print(f"    RPM Bucket: [{bar}] {tokens:.1f}/{rpm_limit} tokens")
            print(f"    RPD:        {rpd_str}")
        print()

# ──────────────────────────────────────────────
# 設定ローダー（.env 優先 / config.json フォールバック）
# ──────────────────────────────────────────────

def _parse_env_file(env_path: Path) -> dict[str, str]:
    """
    .env ファイルをパースして {KEY: VALUE} の辞書を返す。
    標準ライブラリのみ使用（python-dotenv 不要）。
    対応形式:
      KEY=VALUE
      KEY="VALUE"
      KEY='VALUE'
      # コメント行は無視
    """
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # クォート除去
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        result[key] = val
    return result


def _generate_env_template(env_path: Path):
    template = """\
# ==============================================
# unimog / Gemini Agent 設定ファイル
# ==============================================
# Gemini APIキー（Google AI Studio で取得）
# https://aistudio.google.com/app/apikey

GEMINI_KEY_1=YOUR_API_KEY_1
GEMINI_KEY_2=YOUR_API_KEY_2
GEMINI_KEY_3=YOUR_API_KEY_3

# 使用するモデル名（3アカウント共通）
GEMINI_MODEL=gemini-2.0-flash

# レート制限（無料枠: RPM=15, RPD=1500）
GEMINI_RPM=15
GEMINI_RPD=1500

# システムプロンプト
SYSTEM_PROMPT=あなたは有能なAIアシスタントです。日本語で丁寧に回答してください。
"""
    env_path.write_text(template, encoding="utf-8")



def load_config(base_dir: Optional[str] = None) -> tuple[list[AccountConfig], str]:
    """
    設定を読み込む。
      .env が存在する場合 → GEMINI_KEY_x からアカウントを構築
      存在しない         → テンプレートを生成して終了
    """
    search_dir = Path(base_dir) if base_dir else Path(__file__).parent
    env_path   = search_dir / ".env"

    # ── .env が存在する場合 ──────────────────────────────────────
    if env_path.exists():
        env = _parse_env_file(env_path)
        model      = env.get("GEMINI_MODEL", "gemini-2.0-flash")
        rpm_limit  = int(env.get("GEMINI_RPM", "15"))
        # GEMINI_RPD=0 または GEMINI_RPD=unlimited で RPD無制限モード
        rpd_raw    = env.get("GEMINI_RPD", "1500").strip().lower()
        rpd_limit  = 0 if rpd_raw in ("0", "unlimited", "none", "") else int(rpd_raw)
        system_prompt = env.get("SYSTEM_PROMPT", "")
        # GEMINI_THINKING: HIGH / MEDIUM / LOW / NONE（デフォルト HIGH）
        thinking_level = env.get("GEMINI_THINKING", "HIGH").strip().upper()

        accounts = []
        for i in range(1, 10):  # KEY_1 〜 KEY_9 まで対応
            key = env.get(f"GEMINI_KEY_{i}", "")
            if not key or key.startswith("YOUR_"):
                continue
            # アカウントごとにモデル上書き可能（例: GEMINI_MODEL_2=gemma-4-26b-a4b-it）
            acc_model = env.get(f"GEMINI_MODEL_{i}", model)
            acc_rpm   = int(env.get(f"GEMINI_RPM_{i}", str(rpm_limit)))
            acc_rpd_raw = env.get(f"GEMINI_RPD_{i}", rpd_raw)
            acc_rpd   = 0 if acc_rpd_raw.strip().lower() in ("0","unlimited","none","") else int(acc_rpd_raw)
            accounts.append(AccountConfig(
                name=f"account_{i}",
                api_key=key,
                model=acc_model,
                rpm_limit=acc_rpm,
                rpd_limit=acc_rpd,
                thinking_level=thinking_level,
            ))

        if not accounts:
            print("[エラー] .env ファイルに有効な GEMINI_KEY_x が見つかりません。")
            print(f"  {env_path} を開いてAPIキーを設定してください。")
            sys.exit(1)

        log.info({"event": "config_loaded", "source": ".env",
                  "accounts": len(accounts)})
        return accounts, system_prompt

    # ── .env が存在しない → テンプレートを生成 ──────────────────
    _generate_env_template(env_path)
    print("=" * 55)
    print("  設定ファイルを生成しました。")
    print("=" * 55)
    print(f"\n  推奨: .env ファイルにAPIキーを設定してください")
    print(f"  場所: {env_path}")
    print()
    print("  設定例:")
    print("    GEMINI_KEY_1=AIzaSyXXXXXXXXXXXXXXXXXXX")
    print("    GEMINI_KEY_2=AIzaSyYYYYYYYYYYYYYYYYYYY")
    print("    GEMINI_KEY_3=AIzaSyZZZZZZZZZZZZZZZZZZZ")
    print()
    print("  設定後、もう一度 unimog2 を実行してください。")
    print("=" * 55)
    sys.exit(0)

# ──────────────────────────────────────────────
# メインループ（対話モード / パイプモード）
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# コマンドハンドラ登録（ExecutionRegistry）
# ──────────────────────────────────────────────

MODEL_LIST = [
    ("1", "gemma-4-31b-it",     "Gemma 4 31B Dense   — 最高精度・推論最強"),
    ("2", "gemma-4-26b-a4b-it", "Gemma 4 26B MoE     — 高速・精度も高い"),
]


@cmd_registry.register("status", "レート制限状態を表示")
def cmd_status(agent: GeminiAgent, args: str):
    agent.print_status()


@cmd_registry.register("clear", "会話履歴をリセット")
def cmd_clear(agent: GeminiAgent, args: str):
    agent.clear_history()
    print("会話履歴をクリアしました。")


@cmd_registry.register("think", "推論モードの確認・切替 (on/off)")
def cmd_think(agent: GeminiAgent, args: str):
    if args.lower() == "on":
        agent.set_thinking(True)
    elif args.lower() == "off":
        agent.set_thinking(False)
    else:
        state = "ON" if agent.thinking_enabled else "OFF"
        print(f"  現在の推論モード: {state}  (/think on|off で切替)")


@cmd_registry.register("model", "モデルの確認・切替 (/model 1|2|<名前>)")
def cmd_model(agent: GeminiAgent, args: str):
    if not args:
        current = agent.rotator.accounts[0].model
        print("  利用可能なモデル:")
        for num, name, desc in MODEL_LIST:
            marker = " <<" if name == current else ""
            print(f"    {num}: {desc}{marker}")
        print("  切替例: /model 1")
        return
    matched = None
    for num, name, desc in MODEL_LIST:
        if args == num or args == name:
            matched = (name, desc)
            break
    if matched:
        new_model, desc = matched
        for acc in agent.rotator.accounts:
            acc.model = new_model
        agent.clear_history()
        print(f"  モデル変更: {desc}")
        print("  会話履歴をリセットしました。")
    else:
        for acc in agent.rotator.accounts:
            acc.model = args
        agent.clear_history()
        print(f"  モデルを変更しました: {args}")
        print("  会話履歴をリセットしました。")


@cmd_registry.register("cd", "作業フォルダの確認・変更 (/cd <パス>)")
def cmd_cd(agent: GeminiAgent, args: str):
    if not args:
        print(f"  現在の作業フォルダ: {agent.cwd}")
        return
    new_path = args.strip().strip('"').strip("'")
    expanded = str(Path(new_path).expanduser().resolve())
    if Path(expanded).exists():
        agent.set_cwd(expanded)
    else:
        print(f"  フォルダが見つかりません: {expanded}")


@cmd_registry.register("task", "タスクの確認・開始 (/task <ゴール> | end)")
def cmd_task(agent: GeminiAgent, args: str):
    if args.lower() == "end":
        agent.end_task()
        print("  タスクを終了しました。")
    elif args:
        agent.start_task(args)
        print(f"  タスク開始: {args}")
    else:
        if agent._task_goal:
            print(f"  現在のタスク: {agent._task_goal}")
        else:
            print("  タスクなし（/task <ゴール> で開始）")


@cmd_registry.register("context", "現在の作業フォルダを表示")
def cmd_context(agent: GeminiAgent, args: str):
    print(f"  作業フォルダ: {agent.cwd}")


@cmd_registry.register("help", "コマンド一覧を表示")
def cmd_help(agent: GeminiAgent, args: str):
    print(cmd_registry.help_text())


def interactive_loop(
    agent: "GeminiAgent",
    orchestrator: "AgentOrchestrator",
    interactive_orch: "InteractiveOrchestrator",
    auto_git: "AutoGit",
    react_prompt: str,
    plan_prompt: str,
):
    """
    ハイブリッドエージェントのメインループ（Plan-and-Execute モード固定）。
    """
    current_mode = "plan"

    def _mode_label(mode: str) -> str:
        return C.green("Plan-and-Execute")

    @cmd_registry.register("undo", "Auto-Git でロールバック (/undo)")
    def cmd_undo(a: "GeminiAgent", args: str):
        result = auto_git.rollback(a.cwd)
        print(C.yellow(f"  [AutoGit] {result}"))

    @cmd_registry.register("diff", "バックアップからの差分を表示 (/diff)")
    def cmd_diff(a: "GeminiAgent", args: str):
        out = auto_git.diff(a.cwd)
        print(C.gray("  [AutoGit diff]"))
        print(out)

    @cmd_registry.register("history", "ReActログを表示 (/history)")
    def cmd_history(a: "GeminiAgent", args: str):
        interactive_orch.react_log.display()

    @cmd_registry.register("export", "ReActログを Markdown で書き出す (/export [path])")
    def cmd_export(a: "GeminiAgent", args: str):
        path = args.strip() or str(Path(a.cwd) / "react_log.md")
        result = interactive_orch.react_log.export_markdown(path)
        print(C.green(f"  {result}"))

    @cmd_registry.register(
        "autoexport",
        "ReActログの定期自動エクスポート (/autoexport <分> [path] | off | status)"
    )
    def cmd_autoexport(a: "GeminiAgent", args: str):
        rl  = interactive_orch.react_log
        arg = args.strip()

        # ── off: 停止 ─────────────────────────────────────────────
        if arg.lower() in ("off", "stop", "0"):
            rl.stop_auto_export()
            rl._auto_export_path     = None
            rl._auto_export_interval = 0
            print(C.yellow("  [AutoExport] 停止しました。"))
            return

        # ── status: 現在の設定を表示 ──────────────────────────────
        if arg.lower() in ("status", ""):
            if rl.auto_export_enabled:
                mins = rl._auto_export_interval // 60
                secs = rl._auto_export_interval % 60
                interval_str = (f"{mins}分{secs}秒" if secs else f"{mins}分")
                print(C.green(
                    f"  [AutoExport] ON  —  {interval_str}ごと  →  {rl._auto_export_path}"
                ))
            else:
                print(C.gray("  [AutoExport] OFF"))
                print(C.gray("  使い方: /autoexport <分> [保存先パス]"))
                print(C.gray("  例:     /autoexport 5"))
                print(C.gray("          /autoexport 10 C:/logs/session.md"))
            return

        # ── <分> [path]: 有効化 ───────────────────────────────────
        parts = arg.split(maxsplit=1)
        try:
            minutes = float(parts[0])
            if minutes <= 0:
                raise ValueError
        except ValueError:
            print(C.red(f"  エラー: 分数を正の数で指定してください。例: /autoexport 5"))
            return

        interval_sec = int(minutes * 60)
        path = parts[1].strip() if len(parts) > 1 else str(Path(a.cwd) / "react_log.md")

        rl.start_auto_export(path, interval_sec)

        mins = interval_sec // 60
        secs = interval_sec % 60
        interval_str = f"{mins}分{secs}秒" if secs else f"{mins}分"
        print(C.green(f"  [AutoExport] ON  —  {interval_str}ごとに自動保存"))
        print(C.gray(f"  保存先: {path}"))
        print(C.gray("  停止: /autoexport off"))

    # ── ログの定期自動エクスポート ───────────────
    # (既存のコマンド登録はそのまま)

    print(C.cyan(f"  作業フォルダ: {agent.cwd}"))
    print(C.gray(
        "  /help で一覧  ·  exit で終了"
    ) + "\n")

    while True:
        try:
            mode_icon  = C.orange("📋")
            user_input = input(f"{mode_icon} {C.bold_green('❯')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(C.gray("\n終了します。"))
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            print(C.gray("終了します。"))
            break

        match = cmd_registry.route(user_input)
        if match:
            _, handler, args = match
            handler(agent, args)
            continue

        # ── Plan-and-Execute 実行 ──────────────────────────
        _run_plan_ui(orchestrator, user_input)


def pipe_mode(agent: GeminiAgent, prompt: str):
    """
    パイプモード: PowerShell から
      python gemini_agent.py --prompt "質問文"
    のように呼び出す。結果を stdout に出力して終了。
    """
    try:
        response = agent.run(prompt)
        # UTF-8 で stdout に出力（PowerShellの文字化け対策）
        sys.stdout.buffer.write((response + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()
        sys.exit(0)
    except Exception as e:
        msg = f"ERROR: {e}"
        sys.stderr.buffer.write((msg + "\n").encode("utf-8"))
        sys.stderr.buffer.flush()
        log.error({"event": "pipe_error", "error": str(e),
                   "traceback": traceback.format_exc()})
        sys.exit(1)


# ──────────────────────────────────────────────
# Plan-and-Execute マルチエージェント
# ──────────────────────────────────────────────

def _extract_ps_status(result: str) -> str:
    """
    run_powershell の結果テキストからステータス行を抽出する。
    '[SUCCESS]' / '[FAILURE(ExitCode=N)]' / '[FAILURE(TIMEOUT)]' を返す。
    run_powershell を使っていないステップは空文字を返す。
    """
    for line in result.splitlines():
        line = line.strip()
        if line.startswith("[SUCCESS]") or line.startswith("[FAILURE"):
            return line
    return ""


@dataclass
class PlanStep:
    """1ステップの状態を保持するデータクラス"""
    index: int
    description: str
    status: str = "pending"   # pending / running / done / failed / retrying
    result: str = ""
    parallel: bool = False    # True: 前後の parallel=True ステップと並列実行可能


PLANNER_SYSTEM_PROMPT = """\
あなたはタスク計画専門のAIです。
ユーザーのリクエストを受け取り、具体的な実行ステップに分解してください。

# 絶対厳守ルール（最重要）
- **出力はJSONのみ**。前後・途中に一切のテキスト・説明・分析・思考を含めてはならない。
- 思考プロセス（「ユーザーは〜したい」「まず〜を確認する必要がある」等）をJSONの外に書くことは禁止。
- 分析・検討・理由の説明はすべて禁止。ステップの description に凝縮せよ。
- コードブロック（```json など）で囲まない。生のJSONをそのまま出力する。
- 出力の1文字目は必ず `{` でなければならない。

# 出力形式
{"steps":[{"description":"ステップ1の説明","parallel":false},{"description":"ステップ2の説明","parallel":true},{"description":"ステップ3の説明","parallel":true},{"description":"ステップ4の説明","parallel":false}]}

# parallel フィールドのルール
- parallel: true  → 前後の parallel:true ステップと同時並列実行される（互いに独立した作業）
- parallel: false → 前のステップ完了後に逐次実行（前のステップの結果が必要な作業）
- 連続する parallel:true のブロックが並列実行の単位になる
- 例: [false, true, true, false] → Step1 → (Step2 & Step3 同時) → Step4

# その他のルール
- ステップ数は3〜20個（単純なタスクは少なく、複雑なタスクは多く）
- 各ステップの description は具体的かつ実行可能な内容にする（例: 「PowerShellでXXXを実行」）
- description に分析過程・背景説明を含めない。実行する操作のみを記述する。
"""

POWERSHELL_EXECUTOR_GUIDANCE = """\

[PowerShell実行ガイドライン（必須遵守）]
- run_powershell を呼ぶときは working_directory に現在の作業フォルダのフルパスを必ず指定する。
- コマンド結果の先頭が [SUCCESS] なら成功、[FAILURE...] なら失敗。FAILUREは必ずリトライまたは代替手段を取ること。
- ファイルパスはバックスラッシュ（\\）またはJoin-Pathを使うこと。スラッシュは予期しない動作を起こす場合がある。
- 複数行コマンドはヒアストリング(@' ... '@)またはセミコロン区切りで1回のrun_powershellにまとめる。
- 文字コードはrun_powershellが自動でUTF-8に設定する。追加のchcp指定は不要。
- エラー発生時は $Error[0].Exception.Message で詳細を取得して原因を特定してから対処する。
- 変数は同一コマンド内でのみ有効。ステップをまたぐ場合はファイルやレジストリ経由で値を渡す。
"""

REVIEWER_SYSTEM_PROMPT = """\
あなたはタスク検証専門のAIです。
「ステップの目標」と「実行結果」を比較し、目標が達成されたか判定してください。

出力形式（必ずこのJSON形式のみで出力してください）:
{
  "ok": true,
  "reason": "判定理由を1文で"
}

ルール:
- ok=true: 目標が達成された、または部分的に達成されエラーなし
- ok=false: エラーが発生した、または目標が明らかに未達成
- JSONのみを出力し、前後に説明文を加えない
"""

REFLECTOR_SYSTEM_PROMPT = """\
あなたはタスク完了検証の専門家です。
read_file や list_directory ツールを使って実際にファイルや結果を確認し、
クライアントの要望が完全・正確に達成されているか判定してください。

検証手順:
1. タスクで作成・変更・実行されたはずのファイルやリソースを read_file / list_directory で実際に確認する
2. 期待する内容と一致しているか検証する
3. 確認結果に基づいて判定する

最終出力形式（検証完了後に必ずこのJSON形式のみで出力してください）:
{
  "ok": true,
  "issue": "問題がある場合の具体的な修正指示（ok=true の場合は空文字）"
}

ルール:
- ok=true: ファイル内容などを実際に確認し、タスクが完全・正確に達成されたと確認できた
- ok=false: 実際に確認した結果、エラー・未達成・内容の誤りがある
- issue: ok=false の場合のみ、Executor が実行できる具体的な修正内容を記述
- 推測で判定しない。必ずツールで確認してから判定する
- 最終出力はJSONのみ。前後に説明文を加えない
"""

REACT_SYSTEM_PROMPT = """
# Interactive (ReAct) モード 追加指示

## 言語（最重要）
- **すべての出力を日本語で行う**（Thought・最終回答・質問・説明すべて）
- English output is strictly prohibited. Always respond in Japanese.

## 基本フロー
各ターンで「テキスト（Thought）+ ツール呼び出し」または「テキスト（最終回答）のみ」を出力する。

### ツールを使う場合
1. まず状況と方針をテキストで簡潔に述べる（Thought: で始める）
2. 続けてツールを functionCall で呼び出す
3. ツール結果（Observation）を受け取って次のアクションを決める
4. すべて完了したら最終回答をテキストで出力する

### ツールが不要な場合
- 一般的な質問・説明・計算は直接テキストで答える
- ファイル操作・コマンド実行・情報検索・不確かな事実のみツールを使う

## 重要な作業ルール
- **ファイルを編集・上書きする前に必ず read_file で現在の内容を確認する**
- **不明点・確認が必要な事項は ask_user で必ずユーザーに聞く**（推測で重要な判断をしない）
- エラーが出たら内容を分析して原因を特定し、対処策を実行する
- 複数の独立した読み取り操作は同時に呼び出す（並列実行で高速化）
- タスク完了時は「Thought: 完了。」で締めくくり、結果を簡潔にまとめる

## ツール使用の禁止事項
- ツール呼び出しをテキスト内に文字列として書かない（例: 「list_directory を使います」と書くだけで終わらせない）
- 必ず functionCall（API呼び出し）で実行する
- 確認せずにファイルを上書き・削除しない
- 推測だけで重要なファイル操作を行わない

## 【最重要】タスク完了と停止ルール

### タスクが完了したら即座に停止する
- ユーザーが依頼したことをすべて実行したら、**その時点で最終回答を出力して終了する**
- 「他にも直すべき点があるかもしれない」と考えてはならない
- 依頼されていない改善・最適化・リファクタリングを自発的に行ってはならない

### 「もう一つ直そうか」思考パターンの禁止
以下のような内部ループに入ってはならない：
  × 「この問題も修正すべきか？」→「いや、やめておこう」→「でも直した方が良いかも」→（繰り返し）
上記に気づいたら即座に停止し、最終回答を出力する。

### オプション的な問題を見つけた場合
- 依頼の範囲外の問題を発見した場合は、修正せず「メモ: ～という問題も見つかりました。必要であれば別途対応します」と最終回答に一言添えて終了する
- 直すかどうか自分で判断しない。必ずユーザーに委ねる。

### 完了判定チェックリスト（内部確認用）
最終回答を出す前に確認：
1. ユーザーが明示的に依頼したことをすべて実行したか？ → Yes なら終了
2. まだ未完了のステップがあるか？ → No なら終了
3. 次のアクションが「依頼範囲外の改善」だけか？ → Yes なら終了

## 利用可能なツール一覧（参考）
read_file, write_file, edit_file, patch_file, append_file,
create_directory, move_file, copy_file, delete_file,
list_directory, glob, search_files,
run_powershell, web_search, fetch_webpage, wikipedia_search, ask_user
"""


class AgentOrchestrator:
    """
    Plan-and-Execute マルチエージェント オーケストレーター。

    構成:
      Planner  — タスクをステップに分解（ツールなし・thinking OFF）
      Executor — 各ステップをツールで実行（既存 GeminiAgent と同等）
      Reviewer — 結果を検証（ツールなし・thinking OFF）

    Token Bucket 連携:
      - 全エージェントが同じ AccountRotator を共有
      - Reviewer は can_afford_reviewer() が True のときだけ実行
      - wait_to_start() でタスク開始前に RPM 残量を確認・自動待機
    """

    MAX_STEP_RETRY = 2  # 1ステップあたりの最大リトライ回数

    def __init__(self, rotator: "AccountRotator", tool_registry: "ToolRegistry",
                 executor: Optional["GeminiAgent"] = None):
        self.rotator = rotator
        self.tool_registry = tool_registry  # 並列 Executor 生成に使用

        # Planner: ツールなし、軽量
        self.planner = GeminiAgent(rotator, ToolRegistry())
        self.planner.set_system_prompt(PLANNER_SYSTEM_PROMPT)
        self.planner.set_thinking(False, silent=True)

        # Executor: 外部から渡されたインスタンスを使う（main の agent と同一にしてセッション履歴を共有）
        self.executor = executor if executor is not None else GeminiAgent(rotator, tool_registry)

        # Reviewer: ツールなし、thinking OFF でトークン節約
        self.reviewer = GeminiAgent(rotator, ToolRegistry())
        self.reviewer.set_system_prompt(REVIEWER_SYSTEM_PROMPT)
        self.reviewer.set_thinking(False, silent=True)

        # Reflector: 全体タスク完了後の最終検証（read_file・list_directory のみ許可）
        verify_registry = ToolRegistry()
        for spec_name in ("read_file", "list_directory"):
            # グローバル tools レジストリから読み取り系ツールだけを複製
            if spec_name in tool_registry._tools:
                entry = tool_registry._tools[spec_name]
                verify_registry._tools[spec_name] = entry
        self.reflector = GeminiAgent(rotator, verify_registry)
        self.reflector.set_system_prompt(REFLECTOR_SYSTEM_PROMPT)
        self.reflector.set_thinking(False, silent=True)

    def set_executor_system_prompt(self, prompt: str):
        self.executor.set_system_prompt(prompt)

    def _make_executor_agent(self) -> "GeminiAgent":
        """並列実行用に独立した Executor エージェントを生成（状態を共有しない）"""
        a = GeminiAgent(self.rotator, self.tool_registry)
        a.set_system_prompt(self.executor.system_prompt or "")
        a.set_thinking(self.executor.thinking_enabled, silent=True)
        a.cwd = self.executor.cwd
        return a

    def _parse_plan(self, text: str) -> list[dict]:
        """
        Planner の出力からステップリストを抽出。
        Returns: [{"description": str, "parallel": bool}, ...]

        モデルがJSONの前後にテキストを混入させても正しく抽出できるよう、
        brace-matching で全 { ... } 候補を列挙し、
        json.loads が成功して "steps" 配列を持つ最初のものを採用する。
        """
        # ── brace-matching で完全な { ... } ブロックを全て列挙 ──────────
        def _iter_json_candidates(s: str):
            """テキスト中の全 { ... } ブロックをネスト対応で順に yield する"""
            i = 0
            while i < len(s):
                if s[i] == '{':
                    depth = 0
                    start = i
                    for j in range(i, len(s)):
                        if s[j] == '{':
                            depth += 1
                        elif s[j] == '}':
                            depth -= 1
                            if depth == 0:
                                yield s[start:j + 1]
                                i = j  # 次の検索はこのブロックの直後から
                                break
                i += 1

        for candidate in _iter_json_candidates(text):
            try:
                data = json.loads(candidate)
                steps = data.get("steps", [])
                if steps and isinstance(steps, list) and len(steps) > 0:
                    result = []
                    for s in steps[:20]:
                        if isinstance(s, dict):
                            result.append({
                                "description": str(s.get("description", s)),
                                "parallel": bool(s.get("parallel", False)),
                            })
                        else:
                            result.append({"description": str(s), "parallel": False})
                    return result
            except json.JSONDecodeError:
                continue  # このブロックは無効 → 次の候補へ

        log.warning({"event": "plan_json_not_found", "text_preview": text[:200]})

        # フォールバック: 行分割（parallel=False で逐次実行）
        # "Step N:" や箇条書き記号を除去して description のみ残す
        cleaned = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # "Step 1: ..." や "* ..." や "- ..." の先頭記号を除去
            line = re.sub(r'^(Step\s*\d+\s*[:：]\s*|\*\s+|-\s+|\d+\.\s+)', '', line)
            if line:
                cleaned.append(line)
        log.warning({"event": "plan_fallback_to_lines", "line_count": len(cleaned)})
        return [{"description": l, "parallel": False} for l in cleaned[:20]] or \
               [{"description": text, "parallel": False}]

    def _parse_review(self, text: str) -> tuple[bool, str]:
        """Reviewer の出力から ok/reason を抽出"""
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return bool(data.get("ok", True)), data.get("reason", "")
            except json.JSONDecodeError:
                pass
        # フォールバック: エラー文字列を探す
        lower = text.lower()
        if "false" in lower or "失敗" in lower or "エラー" in lower:
            return False, text[:100]
        return True, ""

    @staticmethod
    def _build_review_prompt(description: str, result: str, ps_status: str) -> str:
        """
        Reviewer に渡す構造化プロンプトを生成する。
        ps_status: _extract_ps_status() の戻り値（空文字 = PSコマンドなし）
        """
        lines = [f"ステップの目標: {description}"]
        if ps_status:
            is_fail = ps_status.startswith("[FAILURE")
            lines.append(f"PowerShell実行ステータス: {ps_status}")
            if is_fail:
                lines.append("※ FAILUREはコマンド失敗を意味します。ok=false を強く推奨します。")
        lines.append(f"実行結果（全文）:\n{result[:2000]}")
        return "\n".join(lines)

    def _make_reviewer(self) -> "GeminiAgent":
        """軽量な Reviewer エージェントを生成（ツールなし・thinking OFF）"""
        r = GeminiAgent(self.rotator, ToolRegistry())
        r.set_system_prompt(REVIEWER_SYSTEM_PROMPT)
        r.set_thinking(False, silent=True)
        return r

    def _execute_step(
        self,
        step: "PlanStep",
        all_steps: list["PlanStep"],
        user_message: str,
        agent: "GeminiAgent",
        on_step=None,
        reviewer_pool: Optional[ThreadPoolExecutor] = None,
    ) -> "Optional[Future]":
        """
        単一ステップを実行。

        reviewer_pool が渡された場合（逐次ステップ）:
            Reviewer を非同期投入して即座に次のステップへ進む（オーバーラップ実行）。
            Future を返すので呼び出し元がまとめて結果を収集する。

        reviewer_pool が None の場合（並列ステップ内）:
            Reviewer を同期実行してリトライも行う（従来動作）。
        """
        step.status = "running"
        if on_step:
            on_step(step)

        # 完了済みステップの結果を直近3件まで注入（コンテキスト節約）
        prior_done = [s for s in all_steps if s.index < step.index and s.result]
        if prior_done:
            prior_text = "\n[完了済みステップの結果（参考）]\n" + "\n".join(
                f"  Step {s.index} 「{s.description[:60]}」→ {s.result[:300]}"
                for s in prior_done[-3:]
            ) + "\n"
        else:
            prior_text = ""

        exec_prompt = (
            f"[全体タスク] {user_message}\n"
            f"{prior_text}\n"
            f"[現在のステップ {step.index}/{len(all_steps)}] {step.description}\n"
            f"このステップのみを実行してください。"
        )
        # ストリーミング実行
        step.result = agent.run_stream(
            exec_prompt,
            callback=lambda t: on_step(step, token=t) if on_step else None
        )
        step.status = "done"
        if on_step:
            on_step(step)

        if not self.rotator.can_afford_reviewer():
            return None

        if reviewer_pool is not None:
            # ── 非同期 Reviewer（逐次ステップ用）────────────────────
            # 次のステップとオーバーラップして実行。結果は run_with_plan が収集。
            desc    = step.description
            result  = step.result
            parse   = self._parse_review
            make_r  = self._make_reviewer
            ps_st   = _extract_ps_status(result)
            def _async_review():
                return parse(make_r().run(
                    self._build_review_prompt(desc, result, ps_st)
                ))
            return reviewer_pool.submit(_async_review)
        else:
            # ── 同期 Reviewer（並列ステップ用）+ リトライ────────────
            retry = 0
            while retry < self.MAX_STEP_RETRY:
                review_raw = self._make_reviewer().run(
                    self._build_review_prompt(
                        step.description, step.result,
                        _extract_ps_status(step.result)
                    )
                )
                ok, reason = self._parse_review(review_raw)
                if ok:
                    break
                retry += 1
                step.status = "retrying"
                log.info({"event": "step_retry", "step": step.index,
                          "reason": reason, "retry": retry})
                if on_step:
                    on_step(step)
                # ストリーミングリトライ
                step.result = agent.run_stream(
                    exec_prompt,
                    callback=lambda t: on_step(step, token=t) if on_step else None
                )
                step.status = "done"
                if on_step:
                    on_step(step)
            return None

    def _execute_steps_parallel(
        self,
        parallel_steps: list["PlanStep"],
        all_steps: list["PlanStep"],
        user_message: str,
        on_step=None,
    ) -> None:
        """
        独立した複数ステップを ThreadPoolExecutor で並列実行。
        各ステップに独立した GeminiAgent を割り当て、AccountRotator は共有。
        """
        n = len(parallel_steps)
        print(C.orange(f"  ⚡ {n} ステップを並列実行"), flush=True)
        log.info({"event": "parallel_start", "steps": [s.index for s in parallel_steps]})

        agents = [self._make_executor_agent() for _ in range(n)]

        with ThreadPoolExecutor(max_workers=n) as pool:
            futures = {
                pool.submit(
                    self._execute_step, step, all_steps, user_message, agent, on_step
                ): step
                for step, agent in zip(parallel_steps, agents)
            }
            for future in as_completed(futures):
                step = futures[future]
                try:
                    future.result()
                except Exception as e:
                    step.status = "failed"
                    step.result = f"並列実行エラー: {e}"
                    log.error({"event": "parallel_step_error",
                               "step": step.index, "error": str(e)})
                    if on_step:
                        on_step(step)

    @staticmethod
    def _group_into_batches(steps: list["PlanStep"]) -> list[list["PlanStep"]]:
        """
        連続する parallel=True ステップをグループ化して実行バッチを生成する。
        例: [F, T, T, F] → [[F], [T, T], [F]]
        """
        batches: list[list[PlanStep]] = []
        current: list[PlanStep] = []
        for step in steps:
            if step.parallel:
                current.append(step)
            else:
                if current:
                    batches.append(current)
                    current = []
                batches.append([step])
        if current:
            batches.append(current)
        return batches

    def _parse_reflection(self, text: str) -> tuple[bool, str]:
        """Reflector の出力から ok/issue を抽出"""
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                return bool(data.get("ok", True)), data.get("issue", "")
            except json.JSONDecodeError:
                pass
        lower = text.lower()
        if "修正" in lower or "問題" in lower or "エラー" in lower or "失敗" in lower:
            return False, text[:300]
        return True, ""

    def _reflect_and_correct(
        self,
        user_message: str,
        final_result: str,
        steps: list["PlanStep"],
    ) -> str:
        """
        Reflection Loop: 最終結果を振り返り、不備があれば Executor で修正する。
        RPD 無制限なので常時実行。
        """
        self.reflector.clear_history()
        self.reflector.cwd = self.executor.cwd  # 作業フォルダを同期
        step_summary = "\n".join(
            f"  Step {s.index} ({s.status}): {s.description}" for s in steps
        )
        reflection_raw = self.reflector.run(
            f"[タスク] {user_message}\n\n"
            f"[作業フォルダ] {self.executor.cwd}\n\n"
            f"[実行ステップ]\n{step_summary}\n\n"
            f"[Executorの最終報告]\n{final_result[:2000]}\n\n"
            f"read_file や list_directory で実際にファイルを確認し、"
            f"タスクが正確に完了しているか検証してください。"
        )
        ok, issue = self._parse_reflection(reflection_raw)
        if not ok and issue:
            log.info({"event": "reflection_correction", "issue": issue[:120]})
            print(C.yellow(f"  ↻ Reflection: 修正が必要です → {issue[:80]}"), flush=True)
            corrected = self.executor.run(
                f"[Reflection による修正指示]\n{issue}\n\n"
                f"上記の問題を修正して最終結果を出力してください。"
            )
            print(C.bold_green("  ✓ 修正完了"), flush=True)
            return corrected
        else:
            print(C.bold_green("  ✓ Reflection: タスク完了を確認"), flush=True)
        return final_result

    def run_with_plan(
        self,
        user_message: str,
        on_plan=None,
        on_step=None,
        on_token=None,
    ) -> str:
        """
        Plan-and-Execute + 並列実行 + Reflection Loop のメインループ。

        on_plan(steps: list[PlanStep]) — 計画確定時に呼ばれるコールバック
        on_step(step: PlanStep)        — 各ステップ状態更新時に呼ばれるコールバック
        """
        # ── 1. Planner 用トークン確認（1トークン分のみ待機・Reviewer分は含めない）──
        wait = self.rotator.wait_to_start(1)
        if wait > 0.5:
            log.info({"event": "plan_wait", "wait_sec": round(wait, 1)})
            if on_step:
                dummy = PlanStep(0, f"トークン補充待ち: {wait:.1f}秒", "running")
                on_step(dummy)
            time.sleep(wait)

        # ── 2. Planner でステップ作成 ──────────────────────────────
        # clear_history() を呼ばない → 過去の(prompt, JSON)ペアが履歴に残る
        # モデルは「自分の応答は常にJSON」と学習し、JSON崩れを自然に防ぐ
        # 履歴上限: 直近4タスク分（8ターン）に制限してトークン肥大を防ぐ
        MAX_PLANNER_HISTORY = 8
        if len(self.planner.conversation) > MAX_PLANNER_HISTORY:
            self.planner.conversation = self.planner.conversation[-MAX_PLANNER_HISTORY:]

        tool_names = ", ".join(
            t["name"] for t in self.tool_registry.get_specs()
        ) if self.tool_registry.get_specs() else "run_powershell, read_file, write_file, edit_file, search_files, web_search"
        plan_prompt = (
            "以下のタスクを実行ステップのJSONに分解してください。\n\n"
            "【出力ルール・絶対厳守】\n"
            "1. 出力の1文字目は { でなければならない\n"
            '2. 形式: {"steps":[{"description":"操作内容","parallel":false}, ...]}\n'
            "3. descriptionには分析・説明を書かず、実行する操作だけを書く\n"
            "4. parallel: true=前後のtrue同士を並列 / false=逐次\n"
            "5. JSON以外のテキスト・コードブロック・説明は一切出力禁止\n\n"
            f"[OS] Windows 10 / PowerShell\n"
            f"[作業フォルダ] {self.executor.cwd}\n"
            f"[ツール] {tool_names}\n\n"
            f"[タスク]\n{user_message}"
        )
        plan_raw = self.planner.run(plan_prompt)
        steps_desc = self._parse_plan(plan_raw)

        # パース失敗時: 壊れた応答を履歴から除去（モデルが悪い出力を学習しないよう）
        if not steps_desc and len(self.planner.conversation) >= 2:
            self.planner.conversation = self.planner.conversation[:-2]
            log.warning({"event": "planner_history_rollback"})

        steps = [
            PlanStep(index=i + 1, description=d["description"], parallel=d["parallel"])
            for i, d in enumerate(steps_desc)
        ]

        if on_plan:
            on_plan(steps)

        # ── 3. 実際のステップ数で再チェック ────────────────────────
        wait2 = self.rotator.wait_to_start(len(steps))
        if wait2 > 0.5:
            log.info({"event": "plan_wait2", "wait_sec": round(wait2, 1)})
            time.sleep(wait2)

        # ── 4. Executor + Reviewer ループ（並列バッチ + Reviewerオーバーラップ）──
        # ※ clear_history() を呼ばない → セッション中の会話履歴を引き継ぐ
        # Plan開始前に強制コンパクト: Executor初回コールのペイロード肥大を防ぐ
        self.executor._compact_if_needed()
        self.executor.start_task(user_message)
        results: list[str] = []

        batches = self._group_into_batches(steps)

        # 逐次ステップの Reviewer を前ステップ完了後に同期待機するプール
        n_accounts = len(self.rotator.accounts)

        with ThreadPoolExecutor(max_workers=n_accounts) as reviewer_pool:
            pending: Optional[tuple["PlanStep", "Future"]] = None  # 直前の逐次Reviewer

            for batch in batches:
                # ── 前の逐次ステップの Reviewer 結果を待ってから次を開始 ──
                if pending is not None:
                    prev_step, prev_future = pending
                    pending = None
                    try:
                        ok, reason = prev_future.result()
                        if not ok and reason:
                            log.info({"event": "reviewer_flag_sync",
                                      "step": prev_step.index, "reason": reason[:80]})
                            print(C.yellow(
                                f"  ↻ Reviewer(Step {prev_step.index}): {reason[:80]}"
                            ), flush=True)
                            # その場でリトライ（最大 MAX_STEP_RETRY 回）
                            for _ in range(self.MAX_STEP_RETRY):
                                prev_step.status = "retrying"
                                if on_step:
                                    on_step(prev_step)
                                prev_step.result = self.executor.run_stream(
                                    f"[Reviewer からのリトライ指示]\n{reason}\n\n"
                                    f"[全体タスク] {user_message}\n"
                                    f"[再実行ステップ] {prev_step.description}\n"
                                    f"問題を修正して再度実行してください。",
                                    callback=on_token
                                )
                                prev_step.status = "done"
                                if on_step:
                                    on_step(prev_step)
                                # 再検証
                                re_raw = self._make_reviewer().run(
                                    self._build_review_prompt(
                                        prev_step.description, prev_step.result,
                                        _extract_ps_status(prev_step.result)
                                    )
                                )
                                ok2, _ = self._parse_review(re_raw)
                                if ok2:
                                    break
                    except Exception as e:
                        log.warning({"event": "reviewer_sync_error", "error": str(e)})

                if len(batch) == 1:
                    # 逐次実行: Reviewer をバックグラウンド投入し future を保持
                    future = self._execute_step(
                        batch[0], steps, user_message,
                        self.executor, on_step,
                        reviewer_pool=reviewer_pool,
                    )
                    if future is not None:
                        pending = (batch[0], future)
                else:
                    # 並列実行: 各スレッド内で同期 Reviewer（既存動作）
                    self._execute_steps_parallel(batch, steps, user_message, on_step)

            # 最後の逐次ステップの Reviewer を処理
            if pending is not None:
                prev_step, prev_future = pending
                try:
                    ok, reason = prev_future.result()
                    if not ok and reason:
                        print(C.yellow(
                            f"  ↻ Reviewer(Step {prev_step.index}): {reason[:80]}"
                        ), flush=True)
                        correction_result = self.executor.run_stream(
                            f"[Reviewer からの修正指示]\n{reason}\n\n"
                            f"[全体タスク] {user_message}\n"
                            f"[修正対象ステップ] {prev_step.description}\n"
                            f"問題を修正してください。",
                            callback=on_token
                        )
                        steps.append(PlanStep(
                            index=len(steps) + 1,
                            description=f"[Reviewer修正] Step {prev_step.index}",
                            status="done",
                            result=correction_result,
                        ))
                except Exception as e:
                    log.warning({"event": "reviewer_last_error", "error": str(e)})

        for step in steps:
            results.append(f"[Step {step.index}] {step.description}\n{step.result}")

        self.executor.end_task()

        # ── 5. 最終まとめ ───────────────────────────────────────────
        summary_prompt = (
            f"以下のタスクが完了しました。結果を簡潔にまとめてください。\n\n"
            f"タスク: {user_message}\n\n"
            + "\n\n".join(results)
        )
        final_result = self.executor.run_stream(summary_prompt, callback=on_token)

        # ── 6. Reflection Loop（RPD 無制限なので常時実行）──────────
        print(C.gray("\n  [Reflection: 最終結果を検証中...]"), flush=True)
        final_result = self._reflect_and_correct(user_message, final_result, steps)

        return final_result


# ──────────────────────────────────────────────
# InteractiveOrchestrator（ReActモード）
# ──────────────────────────────────────────────

class InteractiveOrchestrator:
    """
    ReAct（Reason + Act）ベースの対話型オーケストレーター。

    フロー:
      1. Auto-Git バックアップ
      2. AI が Thought を出力 → 初回はユーザーが提案を承認
      3. Tool call (Action) を実行 → 結果 (Observation) を AI に戻す
      4. エラーが MAX_AUTO_RETRY 回続いたらユーザー介入を求める
      5. 書き込み系ツール成功後に Auto-Git チェックポイント
      6. ツールなし応答 = 最終回答を返す
    """

    MAX_AUTO_RETRY  = 2   # エラー自動リトライ上限（超えたらユーザー介入）
    MAX_REACT_STEPS = 60  # ReActループ上限

    def __init__(self, agent: "GeminiAgent", auto_git: "AutoGit"):
        self.agent     = agent
        self.auto_git  = auto_git
        self.react_log = ReactLog()

    @staticmethod
    def _fmt_args(args: dict) -> str:
        return ", ".join(f"{k}={repr(v)[:40]}" for k, v in args.items())

    @staticmethod
    def _extract_thought(text: str) -> str:
        """テキストから Thought: 以降を抽出する。なければ全文を返す。"""
        if not text:
            return ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Thought:"):
                return stripped[len("Thought:"):].strip()
        return text.strip()

    def _confirm_write_tool(self, fn_name: str, fn_args: dict) -> Optional[str]:
        """
        edit_file / write_file 実行前に diff を表示してユーザー確認を取る。
        戻り値: None → 承認（実行続行）、str → スキップメッセージ
        """
        _print_write_diff(fn_name, fn_args)
        print(C.yellow(f"  [書き込み確認] {fn_name} を実行しますか？"), flush=True)
        print(C.gray("    y または Enter → 実行"), flush=True)
        print(C.gray("    n             → スキップ"), flush=True)
        try:
            ans = input(C.bold_green("  >>> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "[ユーザーがキャンセル]"
        if ans in ("n", "no"):
            return f"[ユーザーがスキップを選択] {fn_name} はスキップされました"
        return None  # 承認

    def _execute_with_intervention(
        self, fn_name: str, fn_args: dict, error_counts: dict
    ) -> str:
        """
        ツールを実行する。MAX_AUTO_RETRY 回連続エラーが発生したらユーザー介入を求める。
        読み取り系ツールはキャッシュを利用する。
        書き込み系ツールは実行前に diff 表示 + ユーザー確認を行う。
        """
        # ── キャッシュヒット確認（読み取り系のみ）────────────────
        if fn_name in _CACHEABLE_TOOLS:
            cache_key = self.agent._make_cache_key(fn_name, fn_args)
            if cache_key in self.agent._tool_cache:
                cached = self.agent._tool_cache[cache_key]
                print(C.gray(f"    [キャッシュ] {len(cached)}文字 (再取得スキップ)"), flush=True)
                return cached

        # ── 書き込み系: diff表示 + 承認 ──────────────────────────
        if fn_name in ("write_file", "edit_file", "patch_file"):
            skip_msg = self._confirm_write_tool(fn_name, fn_args)
            if skip_msg:
                return skip_msg
        elif fn_name == "delete_file":
            path_del = fn_args.get("path", "?")
            print(C.red(f"\n  [⚠ 削除確認] {path_del} を削除します。元に戻せません（/undo で復元可）"), flush=True)
            print(C.gray("    y または Enter → 削除実行"), flush=True)
            print(C.gray("    n             → スキップ"), flush=True)
            try:
                ans = input(C.bold_green("  >>> ")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "[ユーザーがキャンセル]"
            if ans in ("n", "no"):
                return f"[ユーザーがスキップを選択] delete_file はスキップされました"

        while True:
            try:
                result = self.agent.tools.execute(fn_name, fn_args)
                error_counts[fn_name] = 0
                result_str = self.agent._summarize_if_long(fn_name, str(result))
                # キャッシュ登録 / 書き込み後の無効化
                if fn_name in _CACHEABLE_TOOLS:
                    self.agent._tool_cache[cache_key] = result_str  # type: ignore[possibly-undefined]
                elif fn_name in ("write_file", "edit_file", "patch_file"):
                    self.agent._invalidate_cache_for_path(fn_args.get("path", ""))
                return result_str
            except Exception as e:
                error_counts[fn_name] = error_counts.get(fn_name, 0) + 1
                err_msg = str(e)
                log.error({"event": "react_tool_error", "tool": fn_name,
                           "error": err_msg, "count": error_counts[fn_name]})
                print(C.red(f"\n  ✗ [{fn_name}] エラー: {err_msg}"), flush=True)

                if error_counts[fn_name] < self.MAX_AUTO_RETRY:
                    # まだ上限未満 → エラーテキストをAIに返してAIに対処させる
                    return f"ツール実行エラー: {fn_name}: {err_msg}"

                # 上限到達 → ユーザー介入プロンプト
                print(C.yellow(
                    f"\n  ⚠ {self.MAX_AUTO_RETRY}回連続エラー。AIが自動解決できませんでした。"
                ), flush=True)
                print(C.gray("  どうしますか？"))
                print(C.gray("    r       → リトライ"))
                print(C.gray("    c       → このツールをスキップして続行"))
                print(C.gray("    その他  → 指示を入力してAIに渡す"))
                try:
                    choice = input(C.bold_green("  >>> ")).strip()
                except (EOFError, KeyboardInterrupt):
                    return f"ユーザーによるキャンセル: {err_msg}"

                if choice.lower() == "r":
                    error_counts[fn_name] = 0
                    continue
                elif choice.lower() == "c":
                    return f"[ユーザーがスキップを選択] エラー: {err_msg}"
                else:
                    return f"[ユーザー指示] {choice}\n[元のエラー] {err_msg}"

    def run_react(self, user_message: str) -> str:
        """
        ReActループのメインエントリポイント。

        Thought → Action → Observation を繰り返して最終回答を返す。
        """
        # ── 1. Auto-Git バックアップ ──────────────────────────────
        backup_result = self.auto_git.backup(self.agent.cwd)
        print(C.gray(f"  [AutoGit] {backup_result}"), flush=True)

        # ── 2. メッセージ構築 ─────────────────────────────────────
        self.agent._compact_if_needed()

        ctx    = self.agent._build_context_header()
        task   = self.agent._task_context()
        prefix = "\n\n".join(p for p in [ctx, task] if p)
        aug_message = f"{prefix}\n\n{user_message}" if prefix else user_message

        messages: list[dict] = list(self.agent.conversation)
        old_conv_len = len(self.agent.conversation)  # ツール実行履歴保存用
        messages.append({"role": "user", "content": aug_message})

        step_count   = 0
        first_action = True
        error_counts: dict[str, int] = {}
        write_tools  = {"write_file", "edit_file", "patch_file", "delete_file"}

        # ── 3. ReActループ ───────────────────────────────────────
        while step_count < self.MAX_REACT_STEPS:
            # ストリーミング呼び出し: テキストはリアルタイムで端末に表示される
            text, tool_calls = self.agent._stream_react_call(messages)

            # Ctrl+C 中断
            if text == "__interrupted__":
                return "処理を中断しました。"

            # ── Thought ログ記録（表示はストリーミング済み）────────
            if text:
                thought = self._extract_thought(text)
                if thought:
                    self.react_log.add("thought", content=thought, step=step_count)

            # ── ツールなし = 最終回答（ストリーミング済み）──────────
            if not tool_calls:
                final_text = text or "(応答なし)"
                # ツール実行履歴を含む全ターンを conversation に保存
                self.agent.conversation.append({"role": "user", "content": user_message})
                self.agent.conversation.extend(messages[old_conv_len + 1:])
                self.agent.conversation.append({"role": "assistant", "content": final_text})
                return final_text

            # (初回アクションのグローバル承認を削除。個別のツール実行時に承認を求める。)
            first_action = False

            # ── アシスタント応答をメッセージ履歴に追加（functionCall 正式形式）──
            messages.append({
                "role": "assistant",
                "content": text or "",
                "function_calls": [
                    {"name": tc["name"], "args": tc.get("args", {})}
                    for tc in tool_calls
                ],
            })

            # ── ツール実行（Action → Observation）───────────────
            tool_results: list[dict] = []

            # 書き込み系ツールが含まれる場合は逐次実行（チェックポイント・介入が必要）
            # 読み取り系のみなら並列実行
            has_write_tool = any(tc.get("name", "") in write_tools for tc in tool_calls)

            if len(tool_calls) > 1 and not has_write_tool:
                # ── 並列実行（読み取り系のみ）──────────────────────
                print(C.orange(f"  ⚡ {len(tool_calls)} ツールを並列実行"), flush=True)
                ordered: list[Optional[dict]] = [None] * len(tool_calls)

                def _par_exec(idx_tc: tuple) -> tuple:
                    idx, tc = idx_tc
                    fn_n = tc.get("name", "")
                    fn_a = tc.get("args", {})
                    print(
                        f"\n  {C.bold_green('⚙')} {C.green(fn_n)}"
                        + C.cyan(f"({self._fmt_args(fn_a)})"),
                        flush=True,
                    )
                    self.react_log.add("action", tool=fn_n, args=fn_a, step=step_count)
                    # キャッシュヒット確認
                    if fn_n in _CACHEABLE_TOOLS:
                        ck = self.agent._make_cache_key(fn_n, fn_a)
                        if ck in self.agent._tool_cache:
                            r_str = self.agent._tool_cache[ck]
                            print(C.gray(f"    [キャッシュ] {len(r_str)}文字"), flush=True)
                            self.react_log.add("observation", tool=fn_n, result=r_str[:500], step=step_count)
                            return idx, fn_n, r_str
                    try:
                        r = self.agent.tools.execute(fn_n, fn_a)
                        r_str = self.agent._summarize_if_long(fn_n, str(r))
                        if fn_n in _CACHEABLE_TOOLS:
                            self.agent._tool_cache[ck] = r_str  # type: ignore[possibly-undefined]
                    except Exception as e:
                        r_str = f"ツール実行エラー: {fn_n}: {e}"
                        log.error({"event": "react_tool_error_par", "tool": fn_n, "error": str(e)})
                    obs_preview = r_str[:300].replace("\n", " ")
                    print(C.cyan(f"  👁 {obs_preview}"), flush=True)
                    self.react_log.add("observation", tool=fn_n, result=r_str[:500], step=step_count)
                    return idx, fn_n, r_str

                with ThreadPoolExecutor(max_workers=len(tool_calls)) as tpool:
                    for idx, fn_n, r_str in tpool.map(_par_exec, enumerate(tool_calls)):
                        ordered[idx] = {"tool": fn_n, "result": r_str[:TOOL_OUTPUT_LIMIT]}
                tool_results = ordered  # type: ignore
            else:
                # ── 逐次実行（書き込み系を含む場合・単一ツール）──────
                for tc in tool_calls:
                    fn_name = tc.get("name", "")
                    fn_args = tc.get("args", {})
                    args_preview = self._fmt_args(fn_args)

                    print(
                        f"\n  {C.bold_green('⚙')} {C.green(fn_name)}"
                        + C.cyan(f"({args_preview})"),
                        flush=True,
                    )
                    self.react_log.add("action", tool=fn_name, args=fn_args, step=step_count)

                    result_str = self._execute_with_intervention(fn_name, fn_args, error_counts)

                    # Auto-checkpoint: 書き込み系ツール成功後に自動コミット
                    if fn_name in write_tools and not result_str.startswith("エラー"):
                        self.auto_git.checkpoint(
                            self.agent.cwd, fn_name, fn_args.get("path", "")
                        )

                    obs_preview = result_str[:300].replace("\n", " ")
                    print(C.cyan(f"  👁 {obs_preview}"), flush=True)
                    self.react_log.add(
                        "observation", tool=fn_name,
                        result=result_str[:500], step=step_count
                    )
                    tool_results.append({
                        "tool":   fn_name,
                        "result": result_str[:TOOL_OUTPUT_LIMIT],
                    })

            # ── Observation を functionResponse 形式でメッセージに追加 ───
            messages.append({
                "role": "user",
                "content": "",
                "function_results": [
                    {"name": r["tool"], "result": r["result"]}
                    for r in tool_results
                ],
            })
            step_count += 1

        # ループ上限到達
        fallback = f"(ReActループ上限 {self.MAX_REACT_STEPS} ステップに達しました)"
        self.agent.conversation.append({"role": "user", "content": user_message})
        self.agent.conversation.extend(messages[old_conv_len + 1:])
        self.agent.conversation.append({"role": "assistant", "content": fallback})
        return fallback


def _run_plan_ui(orchestrator: "AgentOrchestrator", task: str):
    """/plan コマンドのハンドラ"""
    def on_plan(steps):
        print(f"\n{C.green_dim('┌─')} {C.bold_green('実行計画')}")
        for s in steps:
            parallel_tag = C.orange(" [並列]") if s.parallel else ""
            print(f"  {C.gray(f'Step {s.index}:')} {C.white(s.description)}{parallel_tag}")
        print(C.green_dim("└" + "─" * 30))
        print()

    def on_step(step, token=None):
        if token is not None:
            print(token, end="", flush=True)
            return

        icons = {
            "running":  C.green("▶"),
            "done":     C.bold_green("✓"),
            "failed":   C.red("✗"),
            "retrying": C.yellow("↻"),
        }
        icon  = icons.get(step.status, " ")
        label = "" if step.index == 0 else C.gray(f"Step {step.index}: ")
        parallel_tag = C.orange(" ⚡") if getattr(step, "parallel", False) else ""
        print(f"  {icon} {label}{step.description}{parallel_tag}", flush=True)

    try:
        # 最終まとめ等のストリーミング用コールバック
        def on_token(t):
            print(t, end="", flush=True)

        result = orchestrator.run_with_plan(
            task, on_plan=on_plan, on_step=on_step, on_token=on_token
        )
        print(f"\n\n{C.green_dim('┌─')} {C.bold_green('完了')}")
        print(render_markdown(result))
        print(C.green_dim("└" + "─" * 20) + "\n")
    except Exception as e:
        print(C.red(f"  ✗ {e}"))


def main():
    print_ascii_art()
    # stdout / stdin を UTF-8 に固定（Windows cp932 文字化け対策）
    import io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    if hasattr(sys.stdin, "buffer"):
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer, encoding="utf-8", errors="replace"
        )

    # ログの stdout 出力を抑制（ファイルのみに絞る）
    _startup_logger = logging.getLogger("gemini_agent")
    _startup_logger.handlers = [
        h for h in _startup_logger.handlers
        if not isinstance(h, logging.StreamHandler)
    ]

    base_dir = str(Path(__file__).parent)
    accounts, system_prompt = load_config(base_dir)
    rotator = AccountRotator(accounts)

    # agent / orchestrator / auto_git / interactive_orch を生成
    # ── agent と orchestrator.executor を同一インスタンスにする ──
    # → /plan・interactive・スラッシュコマンドすべてが同じ会話履歴を共有
    agent        = GeminiAgent(rotator, tools)
    orchestrator = AgentOrchestrator(rotator, tools, executor=agent)
    auto_git     = AutoGit()

    # PowerShell固有ガイダンス + ReAct指示をプロンプトに結合
    plan_prompt  = (system_prompt or "") + POWERSHELL_EXECUTOR_GUIDANCE
    react_prompt = plan_prompt + REACT_SYSTEM_PROMPT

    # デフォルトは interactive モード → react_prompt を設定
    agent.set_system_prompt(react_prompt)
    orchestrator.set_executor_system_prompt(plan_prompt)

    interactive_orch = InteractiveOrchestrator(agent, auto_git)

    # Reviewer のデフォルト状態（cmd_reviewer で参照）
    orchestrator.use_reviewer = True

    # /plan コマンド: 現在のモードに関わらず Plan-and-Execute を単発実行
    @cmd_registry.register("plan", "Plan-and-Execute で実行 (/plan <タスク>)")
    def cmd_plan(agent: GeminiAgent, args: str):
        if not args:
            print("  使い方: /plan <タスク>")
            print("  ヒント: /mode plan で Plan モードに固定切り替えも可能")
            return
        _run_plan_ui(orchestrator, args)

    @cmd_registry.register("reviewer", "Reviewer の ON/OFF を切り替える (/reviewer on|off)")
    def cmd_reviewer(agent: GeminiAgent, args: str):
        a = args.strip().lower()
        if a in ("off", "0", "false"):
            orchestrator.use_reviewer = False
            print(C.yellow("  Reviewer: OFF（ステップ検証をスキップ・高速モード）"))
        elif a in ("on", "1", "true"):
            orchestrator.use_reviewer = True
            print(C.green("  Reviewer: ON（ステップ検証を実行・高精度モード）"))
        else:
            state = C.green("ON") if getattr(orchestrator, "use_reviewer", True) else C.yellow("OFF")
            print(f"  Reviewer: {state}  (/reviewer on|off で切り替え)")

    # コマンドライン引数のパース（簡易版）
    args = sys.argv[1:]
    if "--prompt" in args:
        idx = args.index("--prompt")
        if idx + 1 < len(args):
            prompt = args[idx + 1]
            pipe_mode(agent, prompt)
        else:
            print("--prompt の後に質問文を指定してください。")
            sys.exit(1)
    elif "--status" in args:
        agent.print_status()
        sys.exit(0)
    else:
        interactive_loop(agent, orchestrator, interactive_orch, auto_git,
                         react_prompt, plan_prompt)


if __name__ == "__main__":
    main()