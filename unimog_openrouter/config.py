from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "owl/alpha"
_DEFAULT_CWD: Optional[str] = None


@dataclass
class OpenRouterConfig:
    api_key: str
    model: str = field(default_factory=lambda: _DEFAULT_MODEL)
    system_prompt: str = ""
    site_url: str = "https://github.com/Loser1025/unimog-v4"
    site_name: str = "Unimog OpenRouter"


# Gemini版との互換エイリアス
AccountConfig = OpenRouterConfig


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
        "# unimog OpenRouter エージェント 設定ファイル\n"
        "# =====================================================\n\n"
        "# OpenRouter APIキー (https://openrouter.ai/keys で取得)\n"
        "OPENROUTER_KEY=YOUR_API_KEY_HERE\n\n"
        "# 使用モデル (https://openrouter.ai/models で確認)\n"
        "# OwlAlpha の正確なモデルIDはサイトで要確認\n"
        "OPENROUTER_MODEL=owl/alpha\n\n"
        "# システムプロンプト\n"
        "SYSTEM_PROMPT=あなたは有能なAIアシスタントです。日本語で丁寧に回答してください。\n"
    )
    env_path.write_text(template, encoding="utf-8")


def load_config(base_dir: Optional[str] = None) -> OpenRouterConfig:
    search_dir = Path(base_dir) if base_dir else Path(__file__).parent
    env_path = search_dir / ".env"

    if env_path.exists():
        env = _parse_env_file(env_path)
        api_key = env.get("OPENROUTER_KEY", "")
        if not api_key or api_key.startswith("YOUR_"):
            print("[エラー] .env に有効な OPENROUTER_KEY が設定されていません。")
            print(f"  場所: {env_path}")
            sys.exit(1)
        model = env.get("OPENROUTER_MODEL", _DEFAULT_MODEL)
        system_prompt = env.get("SYSTEM_PROMPT", "")
        return OpenRouterConfig(api_key=api_key, model=model, system_prompt=system_prompt)

    _generate_env_template(env_path)
    print("=" * 55)
    print("  設定ファイルを生成しました。")
    print("=" * 55)
    print(f"\n  場所: {env_path}")
    print("  OPENROUTER_KEY を設定してから再実行してください。")
    print("=" * 55)
    sys.exit(0)
