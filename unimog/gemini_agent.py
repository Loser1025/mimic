"""
gemini_agent.py
===============
claw-code アーキテクチャを参考にした Gemini マルチアカウント AIエージェント

特徴:
- 3アカウント間でのインテリジェントなAPIキーローテーション
- Token Bucket (GCRA) + RPD デュアルレート制限
    RPM: Token Bucket 方式 — 毎分15トークン補充・即時ブロック不要
    RPD: 日次カウンタ — 1500回/日を正確に管理
- 429 / 503 に対する指数バックオフ + ジッター
- PowerShell との安全な連携（UTF-8 BOM なし, exit code 制御）
- JSON構造化ログ（Windows Event Viewer でも読みやすい）
- ツール実行フレームワーク（claw-code の tool harness 相当）

Token Bucket 方式の利点 (openlimit / GCRA 方式より):
  - 固定ウィンドウのリセット境界でバーストが 2 倍になる問題を解消
  - トークンが連続的に補充されるため待ち時間が最短化される
  - deque の O(n) スキャン不要 → 純粋な O(1) 演算
"""

import json
import time
import random
import sys
import os
import logging
import traceback
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field
import urllib.request
import urllib.error

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
    description="ローカルファイルの内容を読み取る",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "読み取るファイルパス"}
        },
        "required": ["path"]
    }
)
def read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return f"エラー: ファイルが見つかりません: {path}"
    return p.read_text(encoding="utf-8", errors="replace")


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
    description="PowerShellコマンドを安全に実行して結果を返す",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "実行するPowerShellコマンド"},
            "timeout": {"type": "integer", "description": "タイムアウト秒数", "default": 30}
        },
        "required": ["command"]
    }
)
def run_powershell(command: str, timeout: int = 30) -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        rc = result.returncode
        parts = [f"ExitCode: {rc}"]
        if out:
            parts.append(f"STDOUT:\n{out}")
        if err:
            parts.append(f"STDERR:\n{err}")
        return "\n".join(parts)
    except subprocess.TimeoutExpired:
        return f"タイムアウト: {timeout}秒経過"
    except FileNotFoundError:
        return "エラー: PowerShellが見つかりません（Windowsで実行してください）"


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

# ──────────────────────────────────────────────
# APIクライアント
# ──────────────────────────────────────────────

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


def _call_gemini_api(account: AccountConfig, messages: list[dict],
                     tool_specs: list[dict]) -> dict:
    """Gemini API を直接呼び出す（urllib のみ使用）"""
    url = f"{GEMINI_API_BASE}/{account.model}:generateContent?key={account.api_key}"

    # Gemini 形式への変換
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        parts = [{"text": m["content"]}]
        contents.append({"role": role, "parts": parts})

    # Gemma 4 は thinkingBudget 非対応。thinking は system prompt の <|think|> トークンで制御。
    is_gemini_thinking_supported = (
        "gemini-2.0" in account.model or
        "gemini-2.5" in account.model or
        "gemini-3" in account.model
    )
    payload: dict[str, Any] = {"contents": contents}
    if is_gemini_thinking_supported:
        thinking_budget_map = {"HIGH": 16384, "MEDIUM": 8192, "LOW": 1024, "NONE": 0}
        thinking_budget = thinking_budget_map.get(account.thinking_level.upper(), 16384)
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
BASE_BACKOFF = 2.0    # 秒
MAX_BACKOFF = 120.0   # 秒
MAX_TOOL_ROUNDS = 20  # 1ターンあたりのツール呼び出し上限


class GeminiAgent:
    """
    claw-code スタイルの エージェントループ:
      user → [API call] → tool calls → [API call] → ... → final answer
    """

    # セッション圧縮: 会話がこのターン数を超えたら古い履歴を切り捨て
    COMPACTION_THRESHOLD = 20

    def __init__(self, rotator: AccountRotator, tool_registry: ToolRegistry):
        self.rotator = rotator
        self.tools = tool_registry
        self.conversation: list[dict] = []
        self.system_prompt: Optional[str] = None
        self.thinking_enabled: bool = True   # /think on|off で切替
        self.cwd: str = str(Path.cwd())      # カレントフォルダ追跡
        self._task_goal: Optional[str] = None  # 現在のタスクゴール

    def set_system_prompt(self, prompt: str):
        self.system_prompt = prompt

    def set_thinking(self, enabled: bool):
        self.thinking_enabled = enabled
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
    def _compact_if_needed(self):
        """
        API呼び出し不要の切り捨て方式 → RPD消費ゼロ。

        保護ルール:
          - conversation[0] (最初のユーザー指示) は常に保持
          - conversation[1] (最初のアシスタント応答) も保持
          - それ以外の古い部分を切り捨て、直近 keep_recent 件を残す
        """
        if len(self.conversation) <= self.COMPACTION_THRESHOLD * 2:
            return

        keep_recent = 8  # 直近4往復（user+assistant×4）を保持
        # 最初の2件（最初の指示）+ 直近 keep_recent 件
        first_pair = self.conversation[:2]
        recent_part = self.conversation[-keep_recent:]
        dropped = len(self.conversation) - 2 - keep_recent

        self.conversation = first_pair + recent_part

        log.info({"event": "compaction_done",
                  "dropped": dropped, "kept": len(self.conversation)})
        print(f"  [会話を自動圧縮しました: {dropped}件削除、最初の指示+直近{keep_recent}件保持]")

    def _api_call_with_retry(self, messages: list[dict]) -> dict:
        """
        Token Bucket 対応リトライループ。

        pick() が ready アカウントを返した場合 → acquire 済みなので record() 不要
        pick() が waiting アカウントを返した場合 → wait 後に record() で acquire
        429/503 受信 → 指数バックオフ後に次の pick() でローテーション
        """
        tool_specs = self.tools.get_specs()
        attempt = 0

        # 推論モードをアカウント設定に一時反映
        effective_thinking = "HIGH" if self.thinking_enabled else "NONE"
        for acc in self.rotator.accounts:
            acc.thinking_level = effective_thinking

        while attempt < MAX_RETRIES:
            account, wait = self.rotator.pick()

            if wait > 0:
                # RPM 待ち: Token Bucket が指定した待ち時間 + 小ジッター
                jitter = random.uniform(0.05, 0.3)
                actual_wait = wait + jitter
                log.info({"event": "rpm_wait", "account": account.name,
                          "wait_sec": round(actual_wait, 2)})
                print(f"  [Rate Limit] 待機中... ({actual_wait:.1f}秒)")
                time.sleep(actual_wait)
                # 待機後にトークンを取得
                self.rotator.record(account)

            # wait == 0 の場合は pick() 内の acquire() でトークン消費済み

            try:
                log.info({"event": "api_call", "account": account.name,
                          "attempt": attempt + 1,
                          "tokens": round(account.bucket.tokens_available, 1),
                          "rpd_left": account.bucket.rpd_remaining})
                response = _call_gemini_api(account, messages, tool_specs)
                log.info({"event": "api_ok", "account": account.name})
                return response

            except RateLimitError as e:
                # 429: API 側のレート制限 → バックオフしてローテーション
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1),
                              MAX_BACKOFF)
                log.warning({"event": "rate_limit_429", "account": account.name,
                             "status": e.status, "msg": e.message,
                             "backoff_sec": round(backoff, 1)})
                time.sleep(backoff)
                attempt += 1

            except ServerError as e:
                backoff = min(BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 2),
                              MAX_BACKOFF)
                log.warning({"event": "server_error", "account": account.name,
                             "status": e.status, "msg": e.message,
                             "backoff_sec": round(backoff, 1)})
                time.sleep(backoff)
                attempt += 1

            except GeminiAPIError as e:
                log.error({"event": "api_error", "account": account.name,
                           "status": e.status, "msg": e.message})
                raise  # 4xx系（キー不正など）はリトライしない

        raise RuntimeError(f"API呼び出し最大リトライ数 ({MAX_RETRIES}) を超えました")

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

    def run(self, user_message: str) -> str:
        """
        エージェントループのエントリポイント。
        user_message に対して最終応答を文字列で返す。
        """
        # 必要に応じて会話を圧縮
        self._compact_if_needed()

        # コンテキストヘッダー + システムプロンプトを先頭に挿入
        context_header = self._build_context_header()
        task_ctx = self._task_context()

        system_parts = []
        if context_header:
            system_parts.append(context_header)
        if task_ctx:
            system_parts.append(task_ctx)
        if self.system_prompt:
            system_parts.append(self.system_prompt)

        messages: list[dict] = []
        if system_parts:
            messages.append({"role": "user", "content": "\n\n".join(system_parts)})
            messages.append({"role": "assistant",
                             "content": "了解しました。指示に従って動作します。"})

        # 会話履歴を追加
        messages.extend(self.conversation)
        messages.append({"role": "user", "content": user_message})

        tool_round = 0

        while tool_round < MAX_TOOL_ROUNDS:
            response = self._api_call_with_retry(messages)
            finish = self._finish_reason(response)
            text = self._extract_text(response)
            tool_calls = self._extract_tool_calls(response)

            log.info({"event": "response", "finish_reason": finish,
                      "has_text": text is not None,
                      "tool_calls": len(tool_calls)})

            # ── ツール呼び出しがある場合 ──
            if tool_calls and finish in ("STOP", "TOOL_CALLS", "OTHER", ""):
                tool_round += 1
                if tool_round > MAX_TOOL_ROUNDS:
                    log.warning({"event": "tool_limit_reached"})
                    break

                # アシスタントの応答をメッセージ履歴に追加
                messages.append({
                    "role": "assistant",
                    "content": text or "(ツール呼び出し中)",
                })

                # ツールを実行してモデルに結果を返す
                tool_results = []
                for tc in tool_calls:
                    fn_name = tc.get("name", "")
                    fn_args = tc.get("args", {})
                    try:
                        result = self.tools.execute(fn_name, fn_args)
                    except Exception as e:
                        result = f"ツール実行エラー: {fn_name}: {e}"
                        log.error({"event": "tool_error", "tool": fn_name,
                                   "error": str(e)})

                    result_str = str(result)
                    tool_results.append({
                        "tool": fn_name,
                        "result": result_str[:4000],  # トークン節約のため切り詰め
                    })
                    log.info({"event": "tool_result", "tool": fn_name,
                              "result_len": len(result_str)})

                # ツール結果をユーザーメッセージとして追加（Gemini の形式）
                result_text = "\n\n".join(
                    f"[ツール: {r['tool']}]\n{r['result']}" for r in tool_results
                )
                messages.append({"role": "user", "content": result_text})
                continue

            # ── 最終応答 ──
            final_text = text or "(応答なし)"

            # 会話履歴を更新
            self.conversation.append({"role": "user", "content": user_message})
            self.conversation.append({"role": "assistant", "content": final_text})

            return final_text

        return "エラー: ツール呼び出しの上限に達しました"

    def clear_history(self):
        self.conversation = []
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
    print("  設定後、もう一度 unimog を実行してください。")
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


def interactive_loop(agent: GeminiAgent):
    """対話モード: PowerShell/ターミナルから直接使用"""
    print("=" * 60)
    print("  Gemini AIエージェント  (終了: exit / quit / Ctrl+C)")
    print("  コマンド: /help で一覧表示")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nエージェントを終了します。")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("終了します。")
            break

        # ExecutionRegistry によるスラッシュコマンドルーティング
        match = cmd_registry.route(user_input)
        if match:
            _, handler, args = match
            handler(agent, args)
            continue

        try:
            print("\n思考中...", flush=True)
            response = agent.run(user_input)
            print(f"\n{response}")
        except RuntimeError as e:
            print(f"\n[エラー] {e}")
            log.error({"event": "runtime_error", "error": str(e)})
        except Exception as e:
            print(f"\n[予期しないエラー] {e}")
            log.error({"event": "unexpected_error", "error": str(e),
                       "traceback": traceback.format_exc()})


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


def main():
    # stdout を UTF-8 に固定（Windows の cp932 対策）
    if sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        import io
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    base_dir = str(Path(__file__).parent)
    accounts, system_prompt = load_config(base_dir)
    rotator = AccountRotator(accounts)
    agent = GeminiAgent(rotator, tools)

    if system_prompt:
        agent.set_system_prompt(system_prompt)

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
        interactive_loop(agent)


if __name__ == "__main__":
    main()