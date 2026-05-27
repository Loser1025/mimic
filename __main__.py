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
    from .config import load_config
    from .agent import OpenRouterAgent, AccountRotator
    from .tools import tools
    from .autogit import AutoGit
    from .orchestrator import (InteractiveOrchestrator, AgentOrchestrator,
                                POWERSHELL_EXECUTOR_GUIDANCE, REACT_SYSTEM_PROMPT)
    from .main import interactive_loop, pipe_mode, auto_mode

    logging.getLogger("openrouter_agent").handlers = [
        h for h in logging.getLogger("openrouter_agent").handlers
        if isinstance(h, logging.FileHandler)]

    base_dir = str(Path(__file__).parent)
    config, system_prompt = load_config(base_dir)

    # 非対話モード（--prompt / --auto-prompt / --status）ではスキップ
    _args = sys.argv[1:]
    if not any(a in _args for a in ("--prompt", "--auto-prompt", "--status")):
        from .config import select_model_interactively
        config.model, config.context_length = select_model_interactively(config.api_keys[0], config.model)

    rotator      = AccountRotator(config)
    agent        = OpenRouterAgent(rotator, tools)
    orchestrator = AgentOrchestrator(rotator, tools, executor=agent)
    auto_git     = AutoGit()

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

    safe_print(C.gray(f"  モデル: {config.model}"))

    args = sys.argv[1:]
    if "--prompt" in args:
        idx = args.index("--prompt")
        pipe_mode(agent, args[idx + 1]) if idx + 1 < len(args) else sys.exit(1)
    elif "--auto-prompt" in args:
        idx = args.index("--auto-prompt")
        auto_mode(interactive_orch, args[idx + 1], orchestrator) if idx + 1 < len(args) else sys.exit(1)
    elif "--status" in args:
        safe_print(f"  モデル: {config.model}")
        safe_print(f"  APIキー: {len(config.api_keys)} 個")
        sys.exit(0)
    else:
        interactive_loop(
            agent, orchestrator, interactive_orch, auto_git,
            react_prompt, plan_prompt,
        )

if __name__ == "__main__":
    main()
