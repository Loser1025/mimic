import os
import json
import time
import random
import sys
import logging
import traceback
import threading
import re
import glob
import subprocess
from pathlib import Path
from typing import Optional, Any, List, Tuple, Dict
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error
import urllib.parse
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# ──────────────────────────────────────────────
# ANSIカラー & UIヘルパー (V4 Matrix Green Theme)
# ──────────────────────────────────────────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    _RG     = "\033[38;2;0;255;0m"      # Razer Green
    _RG_DIM = "\033[38;2;0;64;0m"       # Dark Forest
    _WHITE  = "\033[38;2;220;255;220m"  # Mint White
    _GRAY   = "\033[38;2;80;120;80m"    # Moss Gray
    _PURPLE = "\033[38;2;160;255;120m"  # Pale Lime
    _CYAN   = "\033[38;2;0;255;180m"    # Seafoam Green
    _RED    = "\033[38;2;200;255;0m"    # Toxic Yellow
    _YELLOW = "\033[38;2;140;255;0m"    # Chartreuse
    _MEM    = "\033[38;2;0;230;255m"    # Electric Aqua

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
    def mem(s):        return f"{C._MEM}{s}{C.RESET}"
    @staticmethod
    def bold(s):       return f"{C.BOLD}{s}{C.RESET}"
    @staticmethod
    def bold_green(s): return f"{C.BOLD}{C._RG}{s}{C.RESET}"

def render_markdown(text: str) -> str:
    lines = text.split("\n")
    out = []
    in_code_block = False
    for line in lines:
        if line.startswith("```"):
            in_code_block = not in_code_block
            out.append(C.green_dim("┌─code" if in_code_block else "└─"))
            continue
        if in_code_block:
            out.append(f"  {C._RG_DIM}{line}{C.RESET}")
        elif line.startswith("# "):
            out.append(C.bold_green(line[2:]))
        elif line.startswith("- ") or line.startswith("* "):
            out.append(f"  {C.green('•')} {line[2:]}")
        else:
            out.append(line)
    return "\n".join(out)

_print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)

# ──────────────────────────────────────────────
# レート制限管理 (Token Bucket / RPD)
# ──────────────────────────────────────────────

class TokenBucket:
    def __init__(self, rpm: int, tpm: int):
        self.rpm = rpm
        self.tpm = tpm
        self.tokens_rpm = float(rpm)
        self.tokens_tpm = float(tpm)
        self.last_refill = time.monotonic()
        self.lock = threading.Lock()

    def refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens_rpm = min(float(self.rpm), self.tokens_rpm + elapsed * (self.rpm / 60.0))
        self.tokens_tpm = min(float(self.tpm), self.tokens_tpm + elapsed * (self.tpm / 60.0))
        self.last_refill = now

    def acquire(self, estimated_tokens: int) -> float:
        with self.lock:
            self.refill()
            wait_rpm = (1.0 - self.tokens_rpm) / (self.rpm / 60.0) if self.tokens_rpm < 1.0 else 0.0
            wait_tpm = (estimated_tokens - self.tokens_tpm) / (self.tpm / 60.0) if self.tokens_tpm < estimated_tokens else 0.0
            wait_time = max(0.0, wait_rpm, wait_tpm)
            if wait_time == 0:
                self.tokens_rpm -= 1.0
                self.tokens_tpm -= estimated_tokens
            return wait_time

# ──────────────────────────────────────────────
# Auto-Git (自動バックアップ)
# ──────────────────────────────────────────────

class AutoGit:
    def __init__(self, cwd: Path):
        self.cwd = cwd
        self._init_repo()

    def _run(self, args: List[str]) -> str:
        try:
            res = subprocess.run(["git", "-C", str(self.cwd)] + args, capture_output=True, text=True, encoding="utf-8", errors="replace")
            return res.stdout.strip()
        except Exception as e:
            return f"Git Error: {e}"

    def _init_repo(self):
        if not (self.cwd / ".git").exists():
            self._run(["init"])
            self._run(["config", "user.email", "agent@unimog.local"])
            self._run(["config", "user.name", "Unimog Agent"])

    def commit(self, message: str):
        self._run(["add", "."])
        # 変更がない場合はエラーになるため、チェックしてからコミット
        status = self._run(["status", "--porcelain"])
        if status:
            self._run(["commit", "-m", message])

    def rollback(self):
        res = self._run(["reset", "--hard", "HEAD~1"])
        return f"Rolled back to previous state. {res}"

    def diff(self) -> str:
        return self._run(["diff", "HEAD"])

# ──────────────────────────────────────────────
# 長期記憶 (Lesson DB / RAG)
# ──────────────────────────────────────────────

class LongTermMemory:
    def __init__(self, db_path: Path, embedder: 'GeminiEmbeddingClient'):
        self.db_path = db_path
        self.embedder = embedder
        self.lessons = self._load_db()

    def _load_db(self) -> List[dict]:
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text(encoding="utf-8"))
            except: pass
        return []

    def save_db(self):
        self.db_path.write_text(json.dumps(self.lessons, ensure_ascii=False, indent=2), encoding="utf-8")

    def query(self, text: str, top_k: int = 3) -> str:
        if not self.lessons: return ""
        query_vec = self.embedder.embed(text)
        if not query_vec: return ""

        scored = []
        for lesson in self.lessons:
            vec = lesson.get("embedding", [])
            if len(vec) == len(query_vec):
                # コサイン類似度 (正規化済み想定)
                score = sum(a*b for a, b in zip(query_vec, vec))
                scored.append((score, lesson))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        top_lessons = [l[1]["content"] for l in scored[:top_k]]
        return "\n".join([f"- {l}" for l in top_lessons]) if top_lessons else ""

    def add_lesson(self, content: str):
        vec = self.embedder.embed(content)
        self.lessons.append({"content": content, "embedding": vec, "timestamp": time.time()})
        self.save_db()

# ──────────────────────────────────────────────
# API クライアント (Groq & Gemini)
# ──────────────────────────────────────────────

class GroqClient:
    def __init__(self, keys: List[str], model: str = "llama-3.3-70b-versatile"):
        self.keys = [k for k in keys if k]
        self.model = model
        self._idx = 0
        self.url = "https://api.groq.com/openai/v1/chat/completions"
        self.bucket = TokenBucket(rpm=30, tpm=60000) # モデルに合わせて調整

    def call(self, messages: List[dict], temperature: float = 0.5) -> str:
        if not self.keys: raise ValueError("Groq APIキーがありません")
        
        est_tokens = (len(str(messages)) // 3) + 1024
        wait_time = self.bucket.acquire(est_tokens)
        if wait_time > 0:
            time.sleep(wait_time)

        key = self.keys[self._idx]
        self._idx = (self._idx + 1) % len(self.keys)

        data = json.dumps({"model": self.model, "messages": messages, "temperature": temperature}).encode("utf-8")
        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                resp = json.loads(res.read().decode("utf-8"))
                return resp["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2)
                return self.call(messages, temperature)
            raise e

class GeminiEmbeddingClient:
    def __init__(self, keys: List[str], model: str = "models/text-embedding-004"):
        self.keys = [k for k in keys if k]
        self.model = model
        self._idx = 0

    def embed(self, text: str) -> List[float]:
        if not self.keys: return []
        key = self.keys[self._idx]
        self._idx = (self._idx + 1) % len(self.keys)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:embedContent?key={key}"
        data = json.dumps({"content": {"parts": [{"text": text}]}}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                resp = json.loads(res.read().decode("utf-8"))
                return resp["embedding"]["values"]
        except: return []

# ──────────────────────────────────────────────
# ツールセット (V4 完全再現 + カテゴリ分け)
# ──────────────────────────────────────────────

class ToolRegistry:
    def __init__(self, cwd: Path):
        self.cwd = cwd
        # READ系 (並列実行可能)
        self.read_tools = ["read_file", "list_directory", "glob", "search_files"]
        self.tools = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "edit_file": self.edit_file,
            "patch_file": self.patch_file,
            "delete_file": self.delete_file,
            "list_directory": self.list_directory,
            "glob": self.glob,
            "search_files": self.search_files,
            "run_powershell": self.run_powershell,
        }

    def execute(self, name: str, args: str) -> str:
        if name not in self.tools: return f"Error: Tool {name} not found."
        try: return self.tools[name](args)
        except Exception as e: return f"Error executing {name}: {str(e)}\n{traceback.format_exc()}"

    def read_file(self, path_str: str) -> str:
        path = self.cwd / path_str.strip().strip('"\'')
        for enc in ["utf-8", "cp932", "euc-jp"]:
            try: return path.read_text(encoding=enc)
            except UnicodeDecodeError: continue
        return path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, block: str) -> str:
        try:
            parts = block.split("\n---\n", 1)
            if len(parts) < 2: return "Error: Invalid format. Use 'path\\n---\\ncontent'"
            path = self.cwd / parts[0].strip().strip('"\'')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(parts[1], encoding="utf-8")
            return f"Success: Wrote to {path}"
        except Exception as e: return f"Error: {e}"

    def edit_file(self, block: str) -> str:
        try:
            lines = block.split("\n")
            path_str = lines[0].strip().strip('"\'')
            content = "\n".join(lines[1:])
            if "---" not in content: return "Error: Use 'path\\nold\\n---\\nnew'"
            old_s, new_s = content.split("---", 1)
            path = self.cwd / path_str
            text = path.read_text(encoding="utf-8")
            if old_s.strip() not in text: return "Error: Old string not found."
            path.write_text(text.replace(old_s.strip(), new_s.strip()), encoding="utf-8")
            return f"Success: Edited {path}"
        except Exception as e: return f"Error: {e}"

    def patch_file(self, block: str) -> str:
        try:
            lines = block.split("\n")
            path_str = lines[0].strip().strip('"\'')
            if "SEARCH" not in block or "REPLACE" not in block: return "Error: Invalid format."
            search_part = block.split("SEARCH")[1].split("REPLACE")[0].strip()
            replace_part = block.split("REPLACE")[1].strip()
            path = self.cwd / path_str
            text = path.read_text(encoding="utf-8")
            if search_part not in text: return "Error: SEARCH block not found."
            path.write_text(text.replace(search_part, replace_part), encoding="utf-8")
            return f"Success: Patched {path}"
        except Exception as e: return f"Error: {e}"

    def delete_file(self, path_str: str) -> str:
        path = self.cwd / path_str.strip().strip('"\'')
        if not path.exists(): return "Error: Not found."
        path.unlink()
        return f"Success: Deleted {path}"

    def list_directory(self, path_str: str) -> str:
        path = self.cwd / path_str.strip().strip('"\'')
        return "\n".join(os.listdir(path))

    def glob(self, pattern: str) -> str:
        return "\n".join(glob.glob(str(self.cwd / pattern.strip().strip('"\'')), recursive=True))

    def search_files(self, query: str) -> str:
        try:
            parts = query.split("\n---\n", 1)
            pattern, regex = parts[0].strip(), parts[1].strip()
            results = []
            for path in self.cwd.glob(pattern):
                if path.is_file():
                    text = self.read_file(str(path))
                    if re.search(regex, text): results.append(str(path))
            return "\n".join(results)
        except Exception as e: return f"Error: {e}"

    def run_powershell(self, code: str) -> str:
        tmp_file = self.cwd / f"tmp_{int(time.time()*1000)}.ps1"
        try:
            with open(tmp_file, "w", encoding="utf-8-sig") as f: f.write(code)
            import subprocess
            res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(tmp_file)], 
                                 capture_output=True, text=True, encoding="cp932", errors="replace")
            return (res.stdout + res.stderr).strip()
        except Exception as e: return f"Error: {e}"
        finally:
            if tmp_file.exists(): tmp_file.unlink()

# ──────────────────────────────────────────────
# インタラクティブ・オーケストレーター
# ──────────────────────────────────────────────

class InteractiveOrchestrator:
    def __init__(self, llm: GroqClient, memory: LongTermMemory, tools: ToolRegistry, git: AutoGit):
        self.llm = llm
        self.memory = memory
        self.tools = tools
        self.git = git
        self.max_react_steps = 15
        self.system_prompt = f"""あなたは有能なAIエージェントです。
以下のツールを使用してユーザーの依頼を完遂してください。
(ツール一覧: read_file, write_file, edit_file, patch_file, delete_file, list_directory, glob, search_files, run_powershell)

【動作形式 (ReAct)】
Thought: 分析と計画
Action: ツール名
Action Input: 引数
Observation: 結果
...
Final Answer: 最終回答
"""

    def run_react(self, user_input: str) -> str:
        # RAG 注入
        lessons = self.memory.query(user_input)
        memory_context = f"\n[過去の教訓]\n{lessons}\n" if lessons else ""
        
        messages = [
            {"role": "system", "content": self.system_prompt + memory_context},
            {"role": "user", "content": user_input}
        ]

        for step in range(self.max_react_steps):
            response = self.llm.call(messages)
            
            if "Thought:" in response:
                thought = response.split("Thought:")[1].split("Action:")[0].strip()
                safe_print(C.purple(f"Thought: {thought}"))

            action_match = re.search(r"Action:\s*(\w+)", response)
            input_match = re.search(r"Action Input:\s*(.*)", response, re.DOTALL)

            if action_match and input_match:
                name = action_match.group(1).strip()
                args = input_match.group(1).strip()
                
                # 危険操作のユーザー介入
                if name == "delete_file":
                    confirm = input(C.red(f"  ⚠ {name} を実行してよろしいですか？ (y/n): "))
                    if confirm.lower() != 'y':
                        observation = "User cancelled the action."
                    else:
                        self.git.commit(f"Before {name}")
                        observation = self.tools.execute(name, args)
                elif name in ["write_file", "edit_file", "patch_file", "run_powershell"]:
                    self.git.commit(f"Before {name}")
                    observation = self.tools.execute(name, args)
                elif name in self.tools.read_tools:
                    # 単一読み取りの場合はそのまま。複数ある場合は本来並列化するが、ここではReActの流れに従う
                    observation = self.tools.execute(name, args)
                else:
                    observation = self.tools.execute(name, args)

                safe_print(C.bold_green(f"Action: {name}"))
                safe_print(C.cyan(f"Observation: {observation[:500]}..."))
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
            elif "Final Answer:" in response:
                res = response.split("Final Answer:")[1].strip()
                # 事後学習: 成功したタスクから教訓を抽出して保存
                self._extract_lesson(user_input, res)
                return res
            else:
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": "Please provide an Action or Final Answer."})

        return "最大ステップ数に達しました。"

    def _extract_lesson(self, task: str, result: str):
        # AIに教訓を抽出させる
        extract_prompt = f"タスク: {task}\n結果: {result}\nこのタスクから得られた技術的な教訓や注意点を1文で抽出してください。なければ 'None' と答えてください。"
        lesson = self.llm.call([{"role": "user", "content": extract_prompt}])
        if "None" not in lesson:
            self.memory.add_lesson(lesson)

# ──────────────────────────────────────────────
# メインエントリーポイント
# ──────────────────────────────────────────────

def main():
    cwd = Path(r"C:\Users\Loser\Desktop\-\-\groqAgent\workspace")
    cwd.mkdir(parents=True, exist_ok=True)

    groq_keys = [os.getenv(f"GROQ_KEY_{i}") for i in range(1, 10)]
    gemini_keys = [os.getenv(f"GEMINI_KEY_{i}") for i in range(1, 10)]

    llm = GroqClient(groq_keys)
    embedder = GeminiEmbeddingClient(gemini_keys)
    git = AutoGit(cwd)
    memory = LongTermMemory(cwd / "lessons_db.json", embedder)
    tools = ToolRegistry(cwd)
    orch = InteractiveOrchestrator(llm, memory, tools, git)

    safe_print(C.bold_green("\n=== GroqAgent V4-Faithful Interactive Mode ==="))
    safe_print(C.gray(f" Working Dir: {cwd}"))
    safe_print(C.gray(" Commands: exit | /undo (Rollback) | /diff (Change) | /help\n"))

    while True:
        try:
            user_input = input(f"{C.green('⚡')} {C.bold_green('❯')} ").strip()
        except (EOFError, KeyboardInterrupt): break

        if not user_input: continue
        if user_input.lower() in ("exit", "quit", "q"): break
        if user_input == "/undo":
            safe_print(C.yellow(git.rollback()))
            continue
        if user_input == "/diff":
            safe_print(C.gray(git.diff()))
            continue
        if user_input == "/help":
            safe_print(C.yellow("Tools: read_file, write_file, edit_file, patch_file, delete_file, list_directory, glob, search_files, run_powershell"))
            continue

        try:
            result = orch.run_react(user_input)
            safe_print(f"\n{C.green_dim('┌─')} {C.bold_green('Agent')}")
            safe_print(render_markdown(result))
            safe_print(C.green_dim("└" + "─" * 20) + "\n")
        except Exception as e:
            safe_print(C.red(f"\n ✗ Error: {e}"))
            safe_print(C.dim(traceback.format_exc()))

if __name__ == "__main__":
    main()
