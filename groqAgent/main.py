import os
import json
import time
import random
import threading
import subprocess
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()

# =================================================================
# 1. ユーティリティ & カラー出力 (V4継承)
# =================================================================

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[38;2;0;255;127m"
    CYAN = "\033[38;2;0;255;255m"
    YELLOW = "\033[38;2;255;255;0m"
    RED = "\033[38;2;255;80;80m"
    MAGENTA = "\033[38;2;255;0;255m"
    BLUE = "\033[38;2;100;149;237m"

_print_lock = threading.Lock()
def safe_print(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)

# =================================================================
# 2. Groq専用レート制限管理 (TPM/RPM Dual Token Bucket)
# =================================================================

class GroqTokenBucket:
    """V4のロジックをベースに、GroqのTPM/RPM制限を厳密に管理"""
    def __init__(self, rpm_limit: int, tpm_limit: int):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self._tokens_rpm = float(rpm_limit)
        self._tokens_tpm = float(tpm_limit)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        # 60秒で全回復するレートで補充
        self._tokens_rpm = min(float(self.rpm_limit), self._tokens_rpm + elapsed * (self.rpm_limit / 60.0))
        self._tokens_tpm = min(float(self.tpm_limit), self._tokens_tpm + elapsed * (self.tpm_limit / 60.0))
        self._last_refill = now

    def acquire(self, estimated_tokens: int) -> Tuple[bool, float]:
        with self._lock:
            self._refill()
            wait_rpm = (1.0 - self._tokens_rpm) / (self.rpm_limit / 60.0) if self._tokens_rpm < 1.0 else 0.0
            wait_tpm = (estimated_tokens - self._tokens_tpm) / (self.tpm_limit / 60.0) if self._tokens_tpm < estimated_tokens else 0.0
            
            wait_time = max(wait_rpm, wait_tpm)
            if wait_time <= 0:
                self._tokens_rpm -= 1.0
                self._tokens_tpm -= estimated_tokens
                return True, 0.0
            return False, wait_time + 0.1 # ネットワーク遅延考慮のマージン

@dataclass
class GroqAccount:
    name: str
    api_key: str
    model: str = "llama-3.3-70b-versatile"
    rpm_limit: int = 30
    tpm_limit: int = 6000
    bucket: GroqTokenBucket = field(init=False)

    def __post_init__(self):
        self.bucket = GroqTokenBucket(self.rpm_limit, self.tpm_limit)

class AccountRotator:
    def __init__(self, accounts: List[GroqAccount]):
        self.accounts = [a for a in accounts if a.api_key]
        self._idx = 0

    def get_available_account(self, tokens: int) -> Tuple[GroqAccount, float]:
        if not self.accounts:
            raise ValueError("有効なAPIキーが設定されていません。.envを確認してください。")
        
        best_wait = float('inf')
        for _ in range(len(self.accounts)):
            acc = self.accounts[self._idx]
            self._idx = (self._idx + 1) % len(self.accounts)
            
            ok, wait_time = acc.bucket.acquire(tokens)
            if ok:
                return acc, 0.0
            best_wait = min(best_wait, wait_time)
        
        return self.accounts[0], best_wait

# =================================================================
# 3. API実行エンジン (指数バックオフ & リトライ)
# =================================================================

class GroqEngine:
    def __init__(self, rotator: AccountRotator):
        self.rotator = rotator
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def execute(self, messages: List[dict], max_tokens: int = 2048, temperature: float = 0.5) -> str:
        # トークン消費の見積もり (入力 + 余裕)
        est_tokens = (len(str(messages)) // 3) + max_tokens
        
        for attempt in range(5): # 最大5回リトライ
            account, wait_time = self.rotator.get_available_account(est_tokens)
            
            if wait_time > 0:
                if attempt > 0:
                    safe_print(C.yellow(f" [!] 全キー制限中... {wait_time:.1f}秒待機します ({account.name})"))
                time.sleep(wait_time)
                continue

            try:
                response = requests.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {account.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": account.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature
                    },
                    timeout=60
                )

                if response.status_code == 429:
                    # 指数バックオフ
                    backoff = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(backoff)
                    continue

                response.raise_for_status()
                res_data = response.json()
                return res_data['choices'][0]['message']['content']

            except Exception as e:
                if attempt == 4:
                    return f"Error: API実行に失敗しました。{str(e)}"
                time.sleep(1)
        
        return "Error: 最大リトライ回数を超過しました。"

        # =================================================================
# 4. ツール実行 (V4継承: PowerShell & ファイル操作)
# =================================================================

class ToolKit:
    @staticmethod
    def run_powershell(code: str) -> str:
        """V4.py 同様、UTF-8-BOM付き一時ファイル経由で安全に実行"""
        script_path = os.path.join("scripts", f"tmp_{int(time.time()*1000)}.ps1")
        safe_print(C.CYAN(f" > [PS Exec]"))
        try:
            # 日本語文字化けを防ぐため UTF-8 with BOM
            with open(script_path, "w", encoding="utf-8-sig") as f:
                f.write(code)
            
            # PowerShell実行 (ExecutionPolicy Bypass)
            res = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path],
                capture_output=True, text=True, encoding="cp932", errors="replace"
            )
            return (res.stdout + res.stderr).strip()
        except Exception as e:
            return f"Error executing PowerShell: {str(e)}"
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

    @staticmethod
    def write_file(filename: str, content: str) -> str:
        path = os.path.join("workspace", filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Success: Wrote to {filename}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

# =================================================================
# 5. ReAct ループエンジン (思考 -> 行動 -> 観察)
# =================================================================

class ReActAgent:
    def __init__(self, engine: GroqEngine):
        self.engine = engine
        self.system_prompt = """あなたは高性能なAIエージェントです。
以下のツールを使用してユーザーの依頼を完遂してください。
ツールを使いたい場合は、必ず以下の形式で出力してください：
Action: powershell
Action Input: (スクリプト内容)

実行結果は Observation: として返されます。解決するまで Thought/Action を繰り返してください。
最後に回答する際は、Final Answer: と記述してください。
"""

    def run(self, user_input: str, max_steps: int = 10):
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input}
        ]
        
        for i in range(max_steps):
            response = self.engine.execute(messages)
            safe_print(C.BOLD + f"\n[Step {i+1}]" + C.RESET + f"\n{response}")
            
            # Actionの抽出
            action_match = re.search(r"Action:\s*(.*)", response)
            action_input_match = re.search(r"Action Input:\s*(.*)", response, re.DOTALL)
            
            if action_match and action_input_match:
                action = action_match.group(1).strip()
                action_input = action_input_match.group(1).strip()
                
                # ツールの実行
                if action.lower() == "powershell":
                    obs = ToolKit.run_powershell(action_input)
                else:
                    obs = f"Unknown tool: {action}"
                
                safe_print(C.BLUE + f"Observation: {obs[:200]}..." + C.RESET)
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {obs}"})
            
            if "Final Answer:" in response:
                return response.split("Final Answer:")[-1].strip()
        
        return "ステップ上限に達しました。"

# =================================================================
# 6. Planner / Executor (V4並列処理ロジック)
# =================================================================

class ParallelOrchestrator:
    def __init__(self, engine: GroqEngine):
        self.engine = engine
        self.use_reviewer = True

    def plan_and_execute_parallel(self, task: str):
        safe_print(C.BOLD + C.MAGENTA + f"\n[Planner] タスクを分解中..." + C.RESET)
        
        # 1. Planning (分解)
        plan_prompt = f"""タスク: {task}
このタスクを並列実行可能なステップに分解してください。
各ステップは 'Step N: 内容' の形式で出力してください。
"""
        plan_output = self.engine.execute([{"role": "user", "content": plan_prompt}])
        steps = re.findall(r"Step \d+: .+", plan_output)
        
        if not steps:
            return self.engine.execute([{"role": "user", "content": task}])

        safe_print(C.YELLOW(f" [Plan] {len(steps)} ステップを検出。並列実行を開始します。"))

        # 2. Execution (並列実行)
        # Groqキーの数（3つ）に合わせて max_workers を制限するのが最適
        results = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_step = {
                executor.submit(self._execute_single_step, step): step for step in steps
            }
            
            for future in as_completed(future_to_step):
                step_name = future_to_step[future]
                try:
                    res = future.result()
                    results[step_name] = res
                    safe_print(C.GREEN(f" [OK] {step_name}"))
                except Exception as e:
                    results[step_name] = f"Error: {e}"
                    safe_print(C.RED(f" [Fail] {step_name}"))

        # 3. Final Summary (統合)
        summary_prompt = f"以下の各ステップの結果を統合し、タスク「{task}」に対する最終的な回答を作成してください。\n結果: {json.dumps(results, ensure_ascii=False)}"
        return self.engine.execute([{"role": "user", "content": summary_prompt}])

    def _execute_single_step(self, step_text: str) -> str:
        """各ステップを独立したリクエストとして処理"""
        # 各ステップでもツールが必要な場合は ReActAgent を呼ぶように拡張可能
        return self.engine.execute([{"role": "user", "content": f"以下の指示を遂行してください: {step_text}"}])
    
    # =================================================================
# 7. セッション記憶管理 (Summarizer)
# =================================================================

class SessionManager:
    """会話履歴の管理と、長くなった場合の自動要約 (V4継承)"""
    def __init__(self, engine: GroqEngine, threshold: int = 15000):
        self.engine = engine
        self.history: List[dict] = []
        self.threshold = threshold  # 文字数しきい値

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        # 履歴が長すぎれば要約
        if len(str(self.history)) > self.threshold:
            self._summarize()

    def _summarize(self):
        safe_print(C.yellow(" [Memory] 履歴が長いため、これまでの内容を要約して圧縮します..."))
        summary_prompt = f"以下の会話履歴を、重要な情報を残して簡潔に要約してください:\n{json.dumps(self.history, ensure_ascii=False)}"
        summary = self.engine.execute([{"role": "user", "content": summary_prompt}], max_tokens=1024)
        
        # 履歴をリセットして要約をシステムプロンプトのように配置
        self.history = [
            {"role": "system", "content": f"これまでの経緯の要約: {summary}"}
        ]

# =================================================================
# 8. ロギングシステム
# =================================================================

class AgentLogger:
    def __init__(self, log_dir: str = "logs"):
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        self.logs = []

    def log_event(self, event_type: str, data: Any):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": data
        }
        self.logs.append(entry)
        with open(self.log_file, "w", encoding="utf-8") as f:
            json.dump(self.logs, f, ensure_ascii=False, indent=2)

# =================================================================
# 9. メイン CLI インターフェース (統合実行部)
# =================================================================

def run_main():
    # 1. 初期設定の読み込み
    config_path = "config/accounts.json"
    if not os.path.exists(config_path):
        safe_print(C.red(f"Error: {config_path} が見つかりません。セットアッププロンプトを実行してください。"))
        return

    # 2. コンポーネントの初期化
    with open(config_path, "r", encoding="utf-8") as f:
        conf_data = json.load(f)
    
    accounts = [GroqAccount(
        name=c['name'],
        api_key=os.getenv(c['api_key_env'], ""),
        model=c['model'],
        rpm_limit=c['rpm_limit'],
        tpm_limit=c['tpm_limit']
    ) for c in conf_data]
    
    rotator = AccountRotator(accounts)
    engine = GroqEngine(rotator)
    session = SessionManager(engine)
    react = ReActAgent(engine)
    orchestrator = ParallelOrchestrator(engine)
    logger = AgentLogger()

    # 3. 起動メッセージ
    safe_print(C.BOLD + C.MAGENTA + "=== Groq Multi-Key Agent V4-G Optimized ===" + C.RESET)
    safe_print(f" [*] 有効なキー数: {len(rotator.accounts)}")
    safe_print(" [!] コマンド: /plan (並列実行), /clear (履歴リセット), exit (終了)\n")

    while True:
        try:
            user_input = input(f"\n{C.CYAN}User > {C.RESET}").strip()
            if not user_input: continue
            if user_input.lower() in ("exit", "quit"): break
            
            if user_input == "/clear":
                session.history = []
                safe_print(C.yellow(" [*] 履歴をリセットしました。"))
                continue

            logger.log_event("user_input", user_input)

            # --- Plan モード (並列実行) ---
            if user_input.startswith("/plan"):
                task = user_input[5:].strip()
                result = orchestrator.plan_and_execute_parallel(task)
                safe_print(f"\n{C.GREEN}Final Summary:{C.RESET}\n{result}")
                logger.log_event("plan_result", result)

            # --- Interactive モード (ReAct) ---
            else:
                # 複雑な依頼（「ファイルを〜」「スクリプトで〜」）が含まれる場合はReActを自動起動
                if any(x in user_input for x in ["ファイル", "実行", "作成", "調査"]):
                    result = react.run(user_input)
                else:
                    # 通常のチャット
                    session.add_message("user", user_input)
                    result = engine.execute(session.history)
                    session.add_message("assistant", result)
                
                safe_print(f"\n{C.GREEN}Groq > {C.RESET}{result}")
                logger.log_event("agent_response", result)

        except KeyboardInterrupt:
            break
        except Exception as e:
            safe_print(C.red(f" [Critical Error] {e}"))
            logger.log_event("error", str(e))

if __name__ == "__main__":
    # 実行前に必要なディレクトリを確認
    for d in ["config", "logs", "workspace", "scripts"]:
        os.makedirs(d, exist_ok=True)
    
    run_main()