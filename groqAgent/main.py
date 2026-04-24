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
    """簡易 Markdown → ANSI レンダラー"""
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
# API クライアント (Groq & Gemini)
# ──────────────────────────────────────────────

class GroqClient:
    def __init__(self, keys: List[str], model: str = "llama-3.3-70b-versatile"):
        self.keys = [k for k in keys if k]
        self.model = model
        self._idx = 0
        self.url = "https://api.groq.com/openai/v1/chat/completions"

    def call(self, messages: List[dict], temperature: float = 0.5) -> str:
        if not self.keys:
            raise ValueError("Groq APIキーが設定されていません。")
        
        # キーローテーション
        key = self.keys[self._idx]
        self._idx = (self._idx + 1) % len(self.keys)

        data = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": temperature
        }).encode("utf-8")

        req = urllib.request.Request(self.url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                resp = json.loads(res.read().decode("utf-8"))
                return resp["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2) # 簡易リトライ
                return self.call(messages, temperature)
            raise e

class GeminiEmbeddingClient:
    def __init__(self, keys: List[str], model: str = "models/text-embedding-004"):
        self.keys = [k for k in keys if k]
        self.model = model
        self._idx = 0

    def embed(self, text: str) -> List[float]:
        if not self.keys:
            return [] # キーがない場合は空リストを返し、RAGをスキップさせる
        
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
        except Exception:
            return []

# ──────────────────────────────────────────────
# ツールセット (V4 完全再現)
# ──────────────────────────────────────────────

class ToolRegistry:
    def __init__(self, cwd: str):
        self.cwd = Path(cwd)
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
        if name not in self.tools:
            return f"Error: Tool {name} not found."
        try:
            return self.tools[name](args)
        except Exception as e:
            return f"Error executing {name}: {str(e)}\n{traceback.format_exc()}"

    def read_file(self, path_str: str) -> str:
        path = self.cwd / path_str.strip().strip('"\'')
        for enc in ["utf-8", "cp932", "euc-jp"]:
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        return path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, content_block: str) -> str:
        # format: path\n---\ncontent
        try:
            parts = content_block.split("\n---\n", 1)
            if len(parts) < 2: return "Error: Invalid format. Use 'path\n---\ncontent'"
            path = self.cwd / parts[0].strip().strip('"\'')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(parts[1], encoding="utf-8")
            return f"Success: Wrote to {path}"
        except Exception as e:
            return f"Error: {e}"

    def edit_file(self, block: str) -> str:
        # format: path\nold\n---\nnew
        try:
            lines = block.split("\n")
            path_str = lines[0].strip().strip('"\'')
            # 簡易的に-sepで分ける
            content = "\n".join(lines[1:])
            if "---" not in content: return "Error: Use 'path\nold_string\n---\nnew_string'"
            old_s, new_s = content.split("---", 1)
            
            path = self.cwd / path_str
            text = path.read_text(encoding="utf-8")
            if old_s.strip() not in text:
                return f"Error: Old string not found in file. {old_s[:50]}..."
            
            new_text = text.replace(old_s.strip(), new_s.strip())
            path.write_text(new_text, encoding="utf-8")
            return f"Success: Edited {path}"
        except Exception as e:
            return f"Error: {e}"

    def patch_file(self, block: str) -> str:
        # V4.py の Search & Replace ブロック方式を模倣
        try:
            lines = block.split("\n")
            path_str = lines[0].strip().strip('"\'')
            # search block and replace block
            if "SEARCH" not in block or "REPLACE" not in block:
                return "Error: Use 'path\nSEARCH\n...\nREPLACE\n...'"
            
            search_part = block.split("SEARCH")[1].split("REPLACE")[0].strip()
            replace_part = block.split("REPLACE")[1].strip()
            
            path = self.cwd / path_str
            text = path.read_text(encoding="utf-8")
            if search_part not in text:
                return "Error: SEARCH block not found exactly."
            
            new_text = text.replace(search_part, replace_part)
            path.write_text(new_text, encoding="utf-8")
            return f"Success: Patched {path}"
        except Exception as e:
            return f"Error: {e}"

    def delete_file(self, path_str: str) -> str:
        path = self.cwd / path_str.strip().strip('"\'')
        if not path.exists(): return "Error: File not found."
        # ユーザー確認はInteractiveOrchestrator側で制御
        path.unlink()
        return f"Success: Deleted {path}"

    def list_directory(self, path_str: str) -> str:
        path = self.cwd / path_str.strip().strip('"\'')
        return "\n".join(os.listdir(path))

    def glob(self, pattern: str) -> str:
        files = glob.glob(str(self.cwd / pattern.strip().strip('"\'')), recursive=True)
        return "\n".join(files)

    def search_files(self, query: str) -> str:
        # format: pattern\n---\nregex
        try:
            parts = query.split("\n---\n", 1)
            pattern, regex = parts[0].strip(), parts[1].strip()
            results = []
            for path in Path(self.cwd).glob(pattern):
                if path.is_file():
                    text = self.read_file(str(path))
                    if re.search(regex, text):
                        results.append(str(path))
            return "\n".join(results)
        except Exception as e:
            return f"Error: {e}"

    def run_powershell(self, code: str) -> str:
        # PowerShell実行。UTF-8-BOM付きの一時ファイルを使用
        tmp_file = self.cwd / f"tmp_{int(time.time()*1000)}.ps1"
        try:
            with open(tmp_file, "w", encoding="utf-8-sig") as f:
                f.write(code)
            import subprocess
            res = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(tmp_file)],
                capture_output=True, text=True, encoding="cp932", errors="replace"
            )
            return (res.stdout + res.stderr).strip()
        except Exception as e:
            return f"Error: {e}"
        finally:
            if tmp_file.exists(): tmp_file.unlink()

# ──────────────────────────────────────────────
# インタラクティブ・オーケストレーター
# ──────────────────────────────────────────────

class InteractiveOrchestrator:
    def __init__(self, llm: GroqClient, embedder: GeminiEmbeddingClient, tools: ToolRegistry):
        self.llm = llm
        self.embedder = embedder
        self.tools = tools
        self.max_react_steps = 15
        self.system_prompt = f"""あなたは有能なAIエージェントです。
以下のツールを使用してユーザーの依頼を完遂してください。

【ツール一覧】
- read_file(path): ファイル内容を読み込む
- write_file(path\\n---\\ncontent): ファイルを新規作成・上書きする
- edit_file(path\\nold\\n---\\nnew): 文字列置換による編集
- patch_file(path\\nSEARCH\\n...\\nREPLACE\\n...): ブロック置換による編集
- delete_file(path): ファイルを削除する
- list_directory(path): ディレクトリ一覧を取得
- glob(pattern): パターン一致ファイルを検索
- search_files(pattern\\n---\\nregex): ファイル内全文検索
- run_powershell(code): PowerShellコマンドを実行

【動作形式 (ReAct)】
1. Thought: 現在の状況を分析し、次に行うべき行動を計画する。
2. Action: 使用するツール名を指定する。例: Action: run_powershell
3. Action Input: ツールに渡す引数を指定する。例: Action Input: Get-Process
4. Observation: ツールの実行結果がここに提供される。

上記を繰り返し、最終的な回答が得られたら以下のように出力して終了してください。
Final Answer: [ユーザーへの回答]
"""

    def run_react(self, user_input: str) -> str:
        # RAG (長期記憶) の擬似実装
        # 実際には lessons_db.json などから埋め込み検索を行うが、ここでは枠組みを実装
        memory_context = ""
        emb = self.embedder.embed(user_input)
        if emb:
            # ここで DB から類似教訓を検索するロジックが入る
            memory_context = "\n[Memory: 過去の類似タスクから得られた教訓をここに注入]\n"

        messages = [
            {"role": "system", "content": self.system_prompt + memory_context},
            {"role": "user", "content": user_input}
        ]

        for step in range(self.max_react_steps):
            response = self.llm.call(messages)
            
            # 思考の表示
            if "Thought:" in response:
                thought = response.split("Thought:")[1].split("Action:")[0].strip()
                safe_print(C.purple(f"Thought: {thought}"))
            else:
                safe_print(C.purple(f"Thought: (分析中...)"))

            # Action の抽出
            action_match = re.search(r"Action:\s*(\w+)", response)
            input_match = re.search(r"Action Input:\s*(.*)", response, re.DOTALL)

            if action_match and input_match:
                action_name = action_match.group(1).strip()
                action_input = input_match.group(1).strip()
                
                safe_print(C.bold_green(f"Action: {action_name}"))
                
                # ツール実行
                observation = self.tools.execute(action_name, action_input)
                safe_print(C.cyan(f"Observation: {observation[:500]}..."))
                
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
            elif "Final Answer:" in response:
                return response.split("Final Answer:")[1].strip()
            else:
                # Action が見つからないが終了していない場合、そのままメッセージに追加して継続
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": "Please provide a tool Action or a Final Answer."})

        return "最大ステップ数に達しました。タスクを完了できませんでした。"

# ──────────────────────────────────────────────
# メインエントリーポイント
# ──────────────────────────────────────────────

def main():
    # パス設定
    cwd = r"C:\Users\Loser\Desktop\-\-\groqAgent\workspace"
    os.makedirs(cwd, exist_ok=True)

    # 環境変数からキーを取得 (マルチキー対応)
    groq_keys = [os.getenv(f"GROQ_KEY_{i}") for i in range(1, 10)]
    gemini_keys = [os.getenv(f"GEMINI_KEY_{i}") for i in range(1, 10)]

    # クライアント初期化
    llm = GroqClient(groq_keys)
    embedder = GeminiEmbeddingClient(gemini_keys)
    tools = ToolRegistry(cwd)
    orch = InteractiveOrchestrator(llm, embedder, tools)

    safe_print(C.bold_green("\n=== GroqAgent Interactive Mode (Llama + Gemini Embedding) ==="))
    safe_print(C.gray(f" Working Dir: {cwd}"))
    safe_print(C.gray(" Commands: exit | quit | /help\n"))

    while True:
        try:
            user_input = input(f"{C.green('⚡')} {C.bold_green('❯')} ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            safe_print(C.gray("終了します。"))
            break
        if user_input == "/help":
            safe_print(C.yellow("Available tools: read_file, write_file, edit_file, patch_file, delete_file, list_directory, glob, search_files, run_powershell"))
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
