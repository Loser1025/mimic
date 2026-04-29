"""
V4.py を NEWUNI/ 配下のモジュールに分割するスクリプト。
- デコレータ行から抽出（@tools.register等に対応）
- ast.Assign のターゲット名を正しく取得
- 全ツール関数・cmd_関数・グローバル変数を対象に含む
"""
import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "V4.py"
DST = Path(__file__).parent

source = SRC.read_text(encoding="utf-8")
lines  = source.splitlines(keepends=True)
tree   = ast.parse(source)

# ── 分割マッピング ────────────────────────────────────────────────
MODULE_MAP: dict[str, str] = {
    # utils.py
    "_print_lock": "utils", "safe_print": "utils",
    "_try_read_file_text": "utils", "C": "utils",
    "render_markdown": "utils", "_render_inline": "utils",
    "print_ascii_art": "utils", "JsonFormatter": "utils",
    "setup_logger": "utils", "TokenBucket": "utils",
    "log": "utils",

    # config.py
    "AccountConfig": "config", "PortContext": "config",
    "build_port_context": "config", "render_port_context": "config",
    "GEMINI_API_BASE": "config",
    "_DEFAULT_MODEL": "config", "_EMBEDDING_MODEL": "config", "_HYDE_MODEL": "config",
    "_generate_env_template": "config",
    "_parse_env_file": "config", "load_config": "config",

    # tools.py — registry + ALL tool functions + constants
    "ExecutionRegistry": "tools", "ToolRegistry": "tools",
    "_READ_FILE_AUTO_CHUNK": "tools", "_pw_context": "tools",
    "tools": "tools",
    "read_file": "tools", "get_repo_map": "tools",
    "write_file": "tools", "run_powershell": "tools",
    "list_directory": "tools", "glob_files": "tools",
    "grep": "tools", "edit_file": "tools",
    "web_search": "tools", "fetch_webpage": "tools",
    "wikipedia_search": "tools", "ask_user": "tools",
    "patch_file": "tools", "delete_file": "tools",
    "create_directory": "tools", "append_file": "tools",
    "move_file": "tools", "copy_file": "tools",
    "_get_browser_page": "tools",
    "browser_navigate": "tools", "browser_click": "tools",
    "browser_type": "tools", "browser_get_text": "tools",
    "browser_screenshot": "tools", "browser_close": "tools",

    # autogit.py
    "AutoGit": "autogit", "ReactLog": "autogit",

    # rag.py — constants + functions
    "_SW_CHUNK_CHARS": "rag", "_SW_OVERLAP_CHARS": "rag",
    "_LESSON_TTL_DAYS": "rag", "_LESSON_MERGE_THRESHOLD": "rag",
    "_TAG_PATTERNS": "rag", "_parse_dt": "rag", "_detect_tags": "rag",
    "_compress_lesson": "rag",
    "get_embedding": "rag", "cosine_similarity": "rag",
    "_rag_tokenize": "rag", "_bm25_scores": "rag",
    "_rrf_combine": "rag", "_hyde_generate": "rag",
    "_sliding_window_chunks": "rag",
    "LongTermMemory": "rag", "SessionRAG": "rag", "ProjectRAG": "rag",

    # agent.py
    "GeminiAPIError": "agent", "RateLimitError": "agent", "ServerError": "agent",
    "MAX_RETRIES": "agent", "BASE_BACKOFF": "agent",
    "MAX_BACKOFF": "agent", "MAX_TOOL_ROUNDS": "agent",
    "TOOL_OUTPUT_LIMIT": "agent", "_CACHEABLE_TOOLS": "agent",
    "_print_write_diff": "agent",
    "_to_gemini_contents": "agent", "_msg_char_count": "agent",
    "_fmt_msg_for_summary": "rag",
    "_trim_messages_smart": "agent",
    "_repair_message_sequence": "agent",
    "_call_gemini_api": "agent", "_stream_gemini_api": "agent",
    "AccountRotator": "agent", "GeminiAgent": "agent",

    # commands.py
    "MODEL_LIST": "commands",
    "cmd_registry": "commands",
    "cmd_status": "commands", "cmd_clear": "commands",
    "cmd_think": "commands", "cmd_model": "commands",
    "cmd_cd": "commands", "cmd_task": "commands",
    "cmd_context": "commands", "cmd_help": "commands",

    # orchestrator.py — classes + system prompts
    "_extract_ps_status": "orchestrator",
    "PlanStep": "orchestrator", "WorkflowGraph": "orchestrator",
    "AgentOrchestrator": "orchestrator",
    "InteractiveOrchestrator": "orchestrator",
    "PLANNER_SYSTEM_PROMPT": "orchestrator",
    "POWERSHELL_EXECUTOR_GUIDANCE": "orchestrator",
    "REVIEWER_SYSTEM_PROMPT": "orchestrator",
    "REFLECTOR_SYSTEM_PROMPT": "orchestrator",
    "REACT_SYSTEM_PROMPT": "orchestrator",

    # main.py
    "GEMINI_RPM": "main", "GEMINI_RPD": "main",
    "_UNIMOG_DONE_MARKER": "main",
    "_run_plan_ui": "main",
    "interactive_loop": "main", "pipe_mode": "main",
    "auto_mode": "main",
}

# ── トップレベルノードから行範囲・名前を取得 ─────────────────────────
def node_info(node) -> tuple[int, int, str]:
    """(start_0based, end_1based, name)"""
    name = ""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        name = node.name
        # デコレータがある場合はデコレータ行から開始
        if getattr(node, "decorator_list", []):
            start = node.decorator_list[0].lineno - 1
        else:
            start = node.lineno - 1
    elif isinstance(node, ast.Assign):
        if node.targets and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        start = node.lineno - 1
    elif isinstance(node, (ast.AnnAssign,)):
        if isinstance(node.target, ast.Name):
            name = node.target.id
        start = node.lineno - 1
    else:
        start = node.lineno - 1
    end = getattr(node, "end_lineno", node.lineno)
    return start, end, name

# ── 各モジュールへのコンテンツ振り分け ──────────────────────────────
module_lines: dict[str, list[str]] = {m: [] for m in set(MODULE_MAP.values())}

for node in ast.iter_child_nodes(tree):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef, ast.Assign, ast.AnnAssign)):
        continue
    start, end, name = node_info(node)
    target = MODULE_MAP.get(name)
    if not target:
        continue
    chunk = lines[start:end]
    module_lines[target].extend(chunk)
    if module_lines[target] and not module_lines[target][-1].endswith("\n"):
        module_lines[target].append("\n")
    module_lines[target].append("\n")

# ── ファイル書き出し ──────────────────────────────────────────────
HEADER = "# Auto-generated by split_v4.py — do not edit manually\n# Original: V4.py\nfrom __future__ import annotations\n\n"

written = []
for mod, content in module_lines.items():
    if not content:
        print(f"  [EMPTY] {mod}.py — skipped")
        continue
    out = DST / f"{mod}.py"
    out.write_text(HEADER + "".join(content), encoding="utf-8")
    written.append(out.name)
    print(f"  [OK] {out.name}  ({len(content)} lines)")

# __init__.py 更新
init = DST / "__init__.py"
mods = sorted(set(MODULE_MAP.values()))
init.write_text("# Auto-generated\n" + "".join(f"from . import {m}\n" for m in mods), encoding="utf-8")
print(f"  [OK] __init__.py")
print(f"\n完了: {len(written)} ファイルを生成")
