from __future__ import annotations

import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"

_DEFAULT_MODEL         = "openrouter/owl-alpha"
_DEFAULT_CWD: Optional[str] = None


@dataclass
class OpenRouterConfig:
    api_keys: list[str]
    model: str = field(default_factory=lambda: _DEFAULT_MODEL)
    system_prompt: str = ""
    site_url: str = "https://github.com/Loser1025/mimic"
    site_name: str = "Mimic OpenRouter"
    rpm_limit: int = 3
    _key_index: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _buckets: list = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        from .utils import TokenBucket
        self._buckets = [TokenBucket(rpm_limit=self.rpm_limit, rpd_limit=0) for _ in self.api_keys]

    @property
    def api_key(self) -> str:
        return self.api_keys[0] if self.api_keys else ""

    def acquire_key(self) -> tuple[str, float]:
        with self._lock:
            n = len(self.api_keys)
            for offset in range(n):
                idx = (self._key_index + offset) % n
                ok, wait = self._buckets[idx].acquire()
                if ok:
                    self._key_index = (idx + 1) % n
                    return self.api_keys[idx], 0.0
            waits = [b.wait_time() for b in self._buckets]
            best = min(range(n), key=lambda i: waits[i])
            return self.api_keys[best], waits[best]

    def next_key(self) -> str:
        with self._lock:
            key = self.api_keys[self._key_index % len(self.api_keys)]
            self._key_index += 1
            return key

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def thinking_level(self) -> str:
        return "NONE"

    @thinking_level.setter
    def thinking_level(self, v: str):
        pass


# ── PortContext (orchestrator.py が使用) ────────────────────────

@dataclass(frozen=True)
class PortContext:
    cwd: Path
    py_file_count: int
    has_tests: bool
    has_config: bool
    top_files: tuple
    py_files: tuple
    cfg_files: tuple


def build_port_context(cwd: Path) -> PortContext:
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


# ── .env パーサー ────────────────────────────────────────────────

def _parse_env_file(env_path: Path) -> dict[str, str]:
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
        if (val.startswith('"') and val.endswith('"')) or \
           (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        result[key] = val
    return result


def _generate_env_template(env_path: Path):
    template = (
        "# =====================================================\n"
        "# Mimic3 設定ファイル\n"
        "# =====================================================\n\n"
        "# ── Actor: OpenRouter (https://openrouter.ai/keys)\n"
        "OPENROUTER_KEY_1=YOUR_API_KEY_1\n"
        "OPENROUTER_KEY_2=YOUR_API_KEY_2\n"
        "OPENROUTER_KEY_3=YOUR_API_KEY_3\n\n"
        "# 使用モデル (https://openrouter.ai/models)\n"
        "OPENROUTER_MODEL=openrouter/owl-alpha\n\n"
        "# レート制限\n"
        "RPM_LIMIT=20\n\n"
        "# システムプロンプト\n"
        "SYSTEM_PROMPT=あなたは有能なAIアシスタントです。日本語で丁寧に回答してください。\n"
    )
    env_path.write_text(template, encoding="utf-8")


def load_config(base_dir: Optional[str] = None) -> tuple[OpenRouterConfig, str]:
    """(config, system_prompt) を返す。"""
    search_dir = Path(base_dir) if base_dir else Path(__file__).parent
    env_path = search_dir / ".env"

    if env_path.exists():
        env = _parse_env_file(env_path)

        global _DEFAULT_MODEL, _DEFAULT_CWD
        _DEFAULT_MODEL = env.get("OPENROUTER_MODEL", _DEFAULT_MODEL)
        _DEFAULT_CWD = os.environ.get("MIMIC_CWD") or env.get("DEFAULT_CWD", None)

        api_keys = []
        for i in range(1, 10):
            k = env.get(f"OPENROUTER_KEY_{i}", "")
            if k and not k.startswith("YOUR_"):
                api_keys.append(k)
        if not api_keys:
            k = env.get("OPENROUTER_KEY", "")
            if k and not k.startswith("YOUR_"):
                api_keys.append(k)

        if not api_keys:
            print("[エラー] .env に有効な OPENROUTER_KEY_1〜3 が見つかりません。")
            sys.exit(1)

        model         = env.get("OPENROUTER_MODEL", _DEFAULT_MODEL)
        system_prompt = env.get("SYSTEM_PROMPT", "")
        rpm_limit     = int(env.get("RPM_LIMIT", "3"))
        return OpenRouterConfig(
            api_keys=api_keys, model=model,
            system_prompt=system_prompt, rpm_limit=rpm_limit,
        ), system_prompt

    _generate_env_template(env_path)
    print("=" * 55)
    print("  設定ファイルを生成しました。")
    print(f"  場所: {env_path}")
    print("  APIキーを設定してから再実行してください。")
    print("=" * 55)
    sys.exit(0)
