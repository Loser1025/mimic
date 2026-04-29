"""NEWUNI エントリポイント — python -m NEWUNI で起動。"""
from __future__ import annotations
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

    from NEWUNI.utils import safe_print, C, print_ascii_art
    import NEWUNI.config as _cfg
    from NEWUNI.config import load_config
    from NEWUNI.agent import GeminiAgent, AccountRotator
    from NEWUNI.tools import tools
    from NEWUNI.rag import LongTermMemory
    from NEWUNI.autogit import AutoGit
    from NEWUNI.orchestrator import (InteractiveOrchestrator, AgentOrchestrator,
                                          POWERSHELL_EXECUTOR_GUIDANCE, REACT_SYSTEM_PROMPT)
    from NEWUNI.main import interactive_loop, pipe_mode, auto_mode

    print_ascii_art()
    logging.getLogger("gemini_agent").handlers = [
        h for h in logging.getLogger("gemini_agent").handlers
        if isinstance(h, logging.FileHandler)]  # FileHandler のみ残す（コンソール出力を削除）

    base_dir = str(Path(__file__).parent)
    accounts, system_prompt = load_config(base_dir)
    rotator = AccountRotator(accounts)

    _G7 = "[38;2;80;220;255m"
    _GR = "[38;2;0;255;80m"
    _DIM = "[2m"
    R = C.RESET
    safe_print(f"{_DIM}  ┌─ Models ────────────────────────────────────────{R}")
    safe_print(f"{_DIM}  │{R}  通常    {_GR}{_cfg._DEFAULT_MODEL}{R}")
    safe_print(f"{_DIM}  │{R}  Embed   {_G7}{_cfg._EMBEDDING_MODEL}{R}")
    safe_print(f"{_DIM}  │{R}  HyDE    {_G7}{_cfg._HYDE_MODEL}{R}")
    safe_print(f"{_DIM}  │{R}  Accounts {_GR}{len(accounts)}{R}")
    safe_print(f"{_DIM}  └─────────────────────────────────────────{R}")
    safe_print()

    long_term_memory = LongTermMemory(str(Path(base_dir) / "lessons_db.json"))
    agent        = GeminiAgent(rotator, tools)
    orchestrator = AgentOrchestrator(rotator, tools, executor=agent, long_term_memory=long_term_memory)
    auto_git     = AutoGit()

    if _cfg._DEFAULT_CWD and Path(_cfg._DEFAULT_CWD).exists():
        agent.cwd = str(Path(_cfg._DEFAULT_CWD).resolve())

    plan_prompt  = (system_prompt or "") + POWERSHELL_EXECUTOR_GUIDANCE
    react_prompt = plan_prompt + REACT_SYSTEM_PROMPT
    agent.set_system_prompt(react_prompt)
    orchestrator.set_executor_system_prompt(plan_prompt)
    interactive_orch = InteractiveOrchestrator(agent, auto_git, long_term_memory=long_term_memory)
    orchestrator.use_reviewer = True

    args = sys.argv[1:]
    if "--prompt" in args:
        idx = args.index("--prompt")
        pipe_mode(agent, args[idx + 1]) if idx + 1 < len(args) else sys.exit(1)
    elif "--auto-prompt" in args:
        idx = args.index("--auto-prompt")
        auto_mode(interactive_orch, args[idx + 1]) if idx + 1 < len(args) else sys.exit(1)
    elif "--status" in args:
        agent.print_status(); sys.exit(0)
    else:
        interactive_loop(agent, orchestrator, interactive_orch, auto_git, react_prompt, plan_prompt)

if __name__ == "__main__":
    main()
