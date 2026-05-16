"""mimic3 エントリポイント — python -m mimic3 で起動。"""
from __future__ import annotations
import os
import sys
import io
import logging
from pathlib import Path

def main():
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stdin, "buffer"):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")

    from .utils import safe_print, C
    from . import config as _cfg
    from .config import load_config, DualConfig
    from .agent import OpenRouterAgent, AccountRotator
    from .tools import tools
    from .autogit import AutoGit
    from .orchestrator import (InteractiveOrchestrator, AgentOrchestrator,
                                DualModelOrchestrator,
                                POWERSHELL_EXECUTOR_GUIDANCE, REACT_SYSTEM_PROMPT)
    from .main import interactive_loop, pipe_mode, auto_mode

    logging.getLogger("openrouter_agent").handlers = [
        h for h in logging.getLogger("openrouter_agent").handlers
        if isinstance(h, logging.FileHandler)]  # FileHandler のみ残す（コンソール出力を削除）

    base_dir = str(Path(__file__).parent)
    config, system_prompt = load_config(base_dir)

    # DualConfig の場合は actor の OpenRouterConfig を取り出す
    is_dual     = isinstance(config, DualConfig)
    actor_cfg   = config.actor if is_dual else config
    rotator     = AccountRotator(actor_cfg)

    agent        = OpenRouterAgent(rotator, tools)
    orchestrator = AgentOrchestrator(rotator, tools, executor=agent)
    auto_git     = AutoGit()

    # MIMIC_CWD (mcp_server.py からの指定) を優先し、次に .env の DEFAULT_CWD を使う
    mimic_cwd = os.environ.get("MIMIC_CWD")
    if mimic_cwd and Path(mimic_cwd).exists():
        agent.cwd = str(Path(mimic_cwd).resolve())
    elif _cfg._DEFAULT_CWD and Path(_cfg._DEFAULT_CWD).exists():
        agent.cwd = str(Path(_cfg._DEFAULT_CWD).resolve())

    plan_prompt  = (system_prompt or "") + POWERSHELL_EXECUTOR_GUIDANCE
    react_prompt = plan_prompt + REACT_SYSTEM_PROMPT
    agent.set_system_prompt(react_prompt)
    orchestrator.set_executor_system_prompt(plan_prompt)
    interactive_orch = InteractiveOrchestrator(agent, auto_git)

    # ── Dual モード: Thinker を初期化（MISTRAL_API_KEY がある場合のみ）──
    dual_orch = None
    if is_dual:
        from .thinker import MistralThinker
        thinker   = MistralThinker(config.thinker, base_system_prompt=system_prompt)
        dual_orch = DualModelOrchestrator(thinker, interactive_orch, auto_git)
        safe_print(C.cyan(
            f"  ✦ Dual モード有効: Thinker={config.thinker.model} / Actor={actor_cfg.model}"
        ))
    else:
        safe_print(C.gray("  シングルモード（MISTRAL_API_KEY 未設定）"))

    args = sys.argv[1:]
    if "--prompt" in args:
        idx = args.index("--prompt")
        pipe_mode(agent, args[idx + 1]) if idx + 1 < len(args) else sys.exit(1)
    elif "--auto-prompt" in args:
        idx = args.index("--auto-prompt")
        auto_mode(interactive_orch, args[idx + 1], orchestrator) if idx + 1 < len(args) else sys.exit(1)
    elif "--status" in args:
        safe_print(f"  モード: {'Dual' if is_dual else 'Single'}")
        safe_print(f"  Actor モデル: {actor_cfg.model}")
        if is_dual:
            safe_print(f"  Thinker モデル: {config.thinker.model}")
        safe_print(f"  APIキー(Actor): {len(actor_cfg.api_keys)} 個")
        sys.exit(0)
    else:
        interactive_loop(
            agent, orchestrator, interactive_orch, auto_git,
            react_prompt, plan_prompt,
            dual_orch=dual_orch,
        )

if __name__ == "__main__":
    main()
