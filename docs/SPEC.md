# Mimic3 独自実装仕様書

> 本ドキュメントは、mimic3 プロジェクトのコードベースにのみ存在する独自機能・独自実装について詳細に記述する。
> 対象モジュール: `thinker.py`, `orchestrator.py`（`DualModelOrchestrator`, `WorkflowGraph`, `AgentOrchestrator`, `InteractiveOrchestrator`）, `agent.py`（`OpenRouterAgent`）, `config.py`, `tools.py`, `utils.py`

---

## 目次

1. [システム全体アーキテクチャ](#1-システム全体アーキテクチャ)
2. [thinker.py — Mistral Thinker（テックリードAI）](#2-thinkerpy--mistral-thinker)
3. [orchestrator.py — 4種のオーケストレーター](#3-orchestratopy--4種のオーケストレーター)
   - 3.1 [WorkflowGraph — グラフベースワークフロー制御](#31-workflowgraph)
   - 3.2 [AgentOrchestrator — Plan-and-Execute](#32-agentorchestrator)
   - 3.3 [InteractiveOrchestrator — ReAct ループ](#33-interactiveorchestrator)
   - 3.4 [DualModelOrchestrator — Thinker + Actor 統合](#34-dualmodelorchestrator)
4. [agent.py — OpenRouterAgent（ReAct エージェント）](#4-agentpy--openrouteragent)
5. [config.py — デュアルモデル設定](#5-configpy--デュアルモデル設定)
6. [tools.py — ツールレジストリと承認フック](#6-toolspy--ツールレジストリ)
7. [utils.py — ユーティリティ群](#7-utilspy--ユーティリティ群)
8. [main.py — 対話ループとモード切替](#8-mainpy--対話ループ)
9. [データフロー図](#9-データフロー図)

---

## 1. システム全体アーキテクチャ

mimic3 は **最大3層のマルチエージェントアーキテクチャ** を採用している。

```
┌─────────────────────────────────────────────────────────────┐
│                    ユーザー (stdin)                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              main.py — interactive_loop()                    │
│  モード切替: interactive / plan / dual                       │
└──────┬──────────────────┬───────────────────┬───────────────┘
       │                  │                   │
       ▼                  ▼                   ▼
┌──────────────┐ ┌────────────────┐  ┌──────────────────────┐
│ Interactive  │ │    Agent       │  │  DualModel           │
│ Orchestrator │ │  Orchestrator  │  │  Orchestrator         │
│ (ReAct)      │ │ (Plan&Execute) │  │  ┌─────────────────┐ │
└──────┬───────┘ └───────┬────────┘  │  │ MistralThinker  │ │
        │                │           │  │ (thinker.py)    │ │
        │                │           │  └────────┬────────┘ │
        ▼                ▼           │           │          │
┌──────────────────────────────┐     │  ┌────────▼────────┐ │
│     OpenRouterAgent          │◄────┘  │ WorkflowGraph   │ │
│     (agent.py)               │        │ + Actor実行     │ │
│  ┌──────────┐ ┌───────────┐  │        └─────────────────┘ │
│  │ReActループ│ │ツール実行 │  │                            │
│  └──────────┘ └───────────┘  │                            │
└──────────────────────────────┘                            │
        │                                                   │
        ▼                                                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    tools.py — ToolRegistry                   │
│  read_file / write_file / edit_file / run_powershell / ...  │
└─────────────────────────────────────────────────────────────┘
```

### 3つの実行モード

| モード | クラス | 説明 |
|--------|--------|------|
| **interactive** | `InteractiveOrchestrator` | ReAct（Reason+Act）ループ。AIが自律的にツールを呼び出して最終回答を導く |
| **plan** | `AgentOrchestrator` | Plan-and-Execute。Planner → Executor → Reviewer の3エージェントが協業 |
| **dual** | `DualModelOrchestrator` | Thinker（Mistral）が計画し、Actor（OwlAlpha）が実行。毎ステップ Thinker が評価・再計画 |

---

## 2. thinker.py — Mistral Thinker

### 概要

Mistral Large 3 を「テックリード」として活用し、**ツール呼び出しを一切行わず** 指示書テキストのみを生成する専用モジュール。

### クラス: `MistralThinker`

```python
class MistralThinker:
    def __init__(self, config: MistralConfig, base_system_prompt: str = "")
```

**設計思想**: Actor（OwlAlpha）に渡す指示書の品質がシステム全体の品質を左右するため、プロンプト設計・エラーハンドリングを丁寧に実装している。

### 主要メソッド

#### `think(user_message: str) -> str`
- Actor への詳細指示書を生成する
- ストリーミング + `render_markdown_thinker`（Aqua テーマ）で表示
- 会話履歴に user/assistant を記録

#### `plan(user_message: str) -> list[dict]`
- ユーザータスクを `PlanStep` リストに分解する
- システムプロンプトを一時的に `THINKER_PLAN_PROMPT` に上書き
- JSON 出力 → `_parse_plan_json()` でパース
- パース失敗時は空リストを返す

#### `review(actor_summary: str) -> str`
- Actor の実行結果をレビューし、完了したこと・残課題・推奨アクションを報告
- `[[TASK_COMPLETE]]` マーカーは Actor の報告後にのみ使用可能

#### `step_review(original_goal, just_executed, step_result, remaining_steps, executed_log) -> dict`
- **1ステップ実行後** に結果を評価し、残りの計画を動的に修正する
- 戻り値:
  ```python
  {"action": "continue", "reason": "..."}                    # 続行
  {"action": "replan", "reason": "...", "steps": [...]}     # 再計画
  {"action": "done", "reason": "..."}                        # 完了
  ```
- パース失敗時は安全側フォールバック `{"action": "continue"}`

### システムプロンプト

| 定数 | 用途 |
|------|------|
| `THINKER_SYSTEM_PROMPT` | デフォルトの Thinker プロンプト（指示書生成） |
| `THINKER_PLAN_PROMPT` | 計画生成専用プロンプト（JSON 出力強制） |
| `THINKER_STEP_REVIEW_PROMPT` | ステップ評価プロンプト（continue/replan/done） |

### JSON パース処理

`_parse_plan_json()` と `_parse_step_decision()` は共通のパイプラインを持つ:

1. コードブロック（` ```json ... ``` `）を剥がす
2. `command` / `content` / `code` フィールドを除去（JSON を壊す複雑な値のため）
3. Brace-matching で全 `{ ... }` ブロックを列挙
4. `json.loads` が成功し、必要なキーを持つ最初のブロックを採用

### エラーハンドリング

| 例外 | 説明 |
|------|------|
| `MistralAPIError` | HTTP エラー（status, message を持つ） |
| `MistralRateLimitError` | 429 レート制限（サブクラス） |

リトライ: 最大 `MAX_RETRIES=4` 回、指数バックオフ（`BASE_BACKOFF=2.0`, `MAX_BACKOFF=30.0`）

### 定数

| 定数 | 値 | 説明 |
|------|-----|------|
| `MAX_RETRIES` | 4 | API リトライ上限 |
| `BASE_BACKOFF` | 2.0 | バックオフ基本秒数 |
| `MAX_BACKOFF` | 30.0 | バックオフ上限秒数 |
| `TASK_COMPLETE_MARKER` | `[[TASK_COMPLETE]]` | タスク完了通知マーカー |

---

## 3. orchestrator.py — 4種のオーケストレーター

### 3.1 WorkflowGraph

#### 概要

`PlanStep` リストを **有向グラフ** として管理し、条件分岐・ジャンプ・共有ステートを制御する。

#### クラス: `PlanStep`

```python
@dataclass
class PlanStep:
    index: int
    description: str
    status: str = "pending"          # pending/running/done/failed/retrying/skipped
    result: str = ""
    parallel: bool = False           # True: 並列実行可能
    label: str = ""                  # goto のジャンプ先ラベル
    on_failure: str = "retry"        # retry/skip/abort/goto:<label>
    on_success: str = ""             # ""(次へ)/goto:<label>/abort
    max_iterations: int = 0          # goto ループ上限（0=安全上限10）
    join_policy: str = "all"         # all/any/first
```

#### エッジ遷移

| directive | 動作 |
|-----------|------|
| `"retry"` | リトライ（`MAX_STEP_RETRY` 回まで） |
| `"skip"` | スキップして次へ |
| `"abort"` | ワークフロー全体を即座に中断 |
| `"goto:<label>"` | 指定ラベルのステップへジャンプ |

#### ループ防止

- `max_iterations > 0` のとき、同一ステップへの goto 回数が上限に達したら `skip` へ格下げ
- 未指定（0）の場合は安全上限 `GOTO_HARD_LIMIT = 10` を適用

#### 共有ステート

```python
graph.state_set("api_key", "abc123")          # キー/値保存
graph.state_get("api_key")                     # → "abc123"
graph.parse_state_updates(result)              # [STATE: key=value] を自動パース
```

- ステップ結果内の `[STATE: key=value]` マーカーを自動検出して更新
- 各ステップのプロンプトに `state_as_text()` が自動注入される
- スレッドセーフ（`_state_lock` による排他制御）

### 3.2 AgentOrchestrator — Plan-and-Execute

#### 概要

**3エージェント協業** による計画実行エンジン。

```
Planner (JSON計画) → Executor (ツール実行) → Reviewer (結果検証)
```

#### クラス: `AgentOrchestrator`

```python
class AgentOrchestrator:
    def __init__(self, rotator, tool_registry, executor=None)
```

#### 主要コンポーネント

| コンポーネント | 説明 |
|---------------|------|
| `planner` | ツールなし、JSON 出力強制（`json_mode=True`） |
| `executor` | ツール付き、外部から渡された `OpenRouterAgent` と同一インスタンス |
| `reviewer` | ツールなし、`ok/reason` の JSON を出力 |
| `reflector` | `read_file` / `list_directory` のみ許可、最終検証 |

#### 実行フロー (`run_with_plan`)

1. **Planner** がタスクをステップに分解（JSON）
2. **WorkflowGraph** を構築
3. ステップをバッチ化（連続する `parallel=True` をグループ化）
4. 逐次ステップ: Reviewer を **非同期投入**（次のステップとオーバーラップ実行）
5. 並列ステップ: `ThreadPoolExecutor` で同時実行、`join_policy` に応じて結合
6. 全ステップ完了後、**Reflection Loop** で最終検証

#### 並列実行バッチ制御

```python
@staticmethod
def _group_into_batches(steps: list[PlanStep]) -> list[list[PlanStep]]
# [F, T, T, F] → [[F], [T, T], [F]]
```

| `join_policy` | 動作 |
|---------------|------|
| `"all"` | 全並列ステップの完了を待つ（デフォルト） |
| `"any"` | いずれか1つが成功した時点で残りをスキップ |
| `"first"` | 成功/失敗を問わず最初に完了した結果で次へ進む |

#### Reviewer オーバーラップ実行

逐次ステップでは、Reviewer を `ThreadPoolExecutor` に非同期投入し、**次のステップの実行と並行** させる。
次のステップ開始前に前ステップの Reviewer 結果を待機し、`on_failure` に応じてリトライ/スキップ/abort/goto を処理する。

#### Reflection Loop (`_reflect_and_correct`)

1. `Reflector` が `read_file` / `list_directory` で実際のファイルを確認
2. `ok=false` の場合、`Executor` に修正指示を出して再実行
3. `ok=true` の場合、タスク完了を確認

### 3.3 InteractiveOrchestrator — ReAct ループ

#### 概要

**Reason + Act** パターンの対話型オーケストレーター。AI が自律的にツールを呼び出して最終回答を導く。

#### クラス: `InteractiveOrchestrator`

```python
class InteractiveOrchestrator:
    def __init__(self, agent: OpenRouterAgent, auto_git: AutoGit)
```

#### ReAct ループ (`run_react`)

```
AutoGit バックアップ
       │
       ▼
Thought (AI が思考をストリーミング出力)
       │
       ├── ツールなし → 最終回答を返す
       │
       ▼
Action (ツール呼び出し)
       │
       ├── 読み取り系のみ → 並列実行（ThreadPoolExecutor）
       └── 書き込み系含む → 逐次実行 + 承認確認
       │
       ▼
Observation (ツール結果を AI に返す)
       │
       └── Thought へ戻る（ループ）
```

#### 主要定数

| 定数 | 値 | 説明 |
|------|-----|------|
| `MAX_AUTO_RETRY` | 2 | エラー自動リトライ上限 |
| `MAX_REACT_STEPS` | 60 | ReAct ループ上限 |

#### 書き込み承認フック

- `set_write_approval_handler()` で登録されたハンドラが、`write_file` / `edit_file` / `patch_file` 実行前に呼ばれる
- ユーザーが `n` を入力 → `UserRejectedWriteError` が送出 → ループ即停止

#### ツールキャッシュ

- 読み取り系ツール（`read_file`, `list_directory`, `search_files`, `get_repo_map`）の結果をキャッシュ
- 書き込み系ツール実行後、関連するキャッシュを自動無効化

#### Auto-Git チェックポイント

- 書き込み系ツール成功後に自動コミット
- エラー・スキップ・キャンセル時はチェックポイントを行わない

#### ReAct ログ (`ReactLog`)

- 全ターンの `thought` / `action` / `observation` を記録
- `/history` で表示、`/export` で Markdown 書き出し
- `/autoexport <分>` で定期自動エクスポート

### 3.4 DualModelOrchestrator — Thinker + Actor 統合

#### 概要

**Mistral Thinker** と **OwlAlpha Actor** の2モデルを統合し、Thinker が計画・評価・再計画を行い、Actor が実行する。

#### クラス: `DualModelOrchestrator`

```python
class DualModelOrchestrator:
    def __init__(self, thinker: MistralThinker, actor_orch: InteractiveOrchestrator, auto_git: AutoGit)
```

#### メインループ (`run`)

```
1. Thinker.plan() → JSON ステップ計画生成
2. ユーザー承認（y/N）
3. _execute_adaptive_workflow() → 適応型ワークフロー実行
4. Thinker.review() → 最終レビュー
5. ユーザーに制御を返す
```

#### 適応型ワークフロー (`_execute_adaptive_workflow`)

各ステップ実行後に **Thinker.step_review()** を呼び出し、残りの計画を動的に修正する:

```
Step 1 実行 (Actor)
    │
    ▼
Thinker.step_review() → continue
    │
    ▼
Step 2 実行 (Actor)
    │
    ▼
Thinker.step_review() → replan (残りステップを差し替え)
    │
    ▼
New Step 3 実行 (Actor)
    │
    ▼
Thinker.step_review() → done (ループ終了)
```

#### 冷却タイマー

- Thinker の連続呼び出しを防ぐため、`_THINKER_COOLDOWN` 秒の冷却期間を設ける
- Actor の実行時間が既に冷却時間を超えていれば即通過
- 初回は即実行できるよう `time.time() - 40` に初期化

#### 計画承認フロー

1. Thinker が計画を生成 → Aqua 枠で表示
2. ユーザーが `y/N` で承認
3. 否決時: Thinker の会話履歴に否決メッセージを追加し、次の指示で別のアプローチを促す
4. 否決時: Thinker の直前ターン（user+assistant）を履歴から削除

#### 定数

| 定数 | 値 | 説明 |
|------|-----|------|
| `MAX_STEP_RETRY` | 2 | 1ステップあたりの最大リトライ回数 |
| `MAX_REPLAN_COUNT` | 3 | 再計画の上限回数 |
| `_THINKER_COOLDOWN` | 40秒 | Thinker 連続呼び出し防止の冷却時間 |

---

## 4. agent.py — OpenRouterAgent

### 概要

OpenRouter API を使った ReAct ループエージェント。ツール定義を持ち、API 呼び出しとツール実行を仲介する。

### クラス: `OpenRouterAgent`

```python
class OpenRouterAgent:
    def __init__(self, config_or_rotator, tool_registry)
```

### 主要機能

#### ReAct ループ

```python
def run(self, user_message: str) -> str:
    # 1. コンテキストヘッダー構築（作業フォルダ + タスク目標）
    # 2. conversation に user メッセージ追加
    # 3. MAX_TOOL_ROUNDS=60 回ループ:
    #    a. API 呼び出し → text + tool_calls 取得
    #    b. tool_calls なし → 最終回答を返す
    #    c. ツール実行（単一=逐次、複数=並列 ThreadPoolExecutor）
    #    d. 結果を conversation に role:tool で追加
```

#### ストリーミング ReAct

```python
def _stream_react_call(self, messages, text_callback=None) -> tuple[str, list]:
    # PipelineTypewriter でバッファ→レンダリング→タイプライター表示
    # (full_text, tool_calls) を返す
```

#### コンテキスト圧縮

```python
COMPACTION_THRESHOLD_CHARS = 3_000_000  # 約75%のコンテキスト使用率で発動
COMPACTION_KEEP_RECENT = 20             # 直近20メッセージを保持
```

会話の総文字数が閾値を超えると、最初の2メッセージ + 削除ノート + 直近20メッセージに圧縮。

#### メッセージ修復

```python
def _repair_message_sequence(messages: list[dict]) -> list[dict]:
    # 孤立した tool_calls / tool ロールメッセージを除去
    # OpenAI ネイティブ形式の整合性を保証
```

#### メッセージトリム

```python
def _trim_messages_smart(messages: list[dict]) -> list[dict]:
    # 古い role:tool メッセージを優先削除
    # 直前の assistant+tool_calls も一緒に削除（孤立防止）
```

#### エラーハイアラキー

```
OpenRouterAPIError (基底)
├── RateLimitError (429)
└── ServerError (5xx)
```

#### リトライ戦略

| エラー | 動作 |
|--------|------|
| 429 RateLimitError | 指数バックオフ + ジッター |
| 5xx ServerError | バックオフ + メッセージトリム |
| 接続エラー | バックオフ + リトライ |
| その他 API エラー | 即座に例外送出 |

リトライ上限: `MAX_RETRIES=5`、`BASE_BACKOFF=2.0`、`MAX_BACKOFF=60.0`

### AccountRotator 互換ラッパー

```python
class AccountRotator:
    def __init__(self, config_or_list)
    def pick() -> tuple[OpenRouterConfig, float]
    def record(account)
    def can_afford_reviewer() -> bool
    def wait_to_start(step_count: int) -> float
```

V4 の `AccountRotator` インタフェースとの互換性を保つラッパー。

---

## 5. config.py — デュアルモデル設定

### 設定読み込みフロー

```
.env ファイル
    │
    ├── MISTRAL_API_KEY あり → DualConfig(thinker, actor)
    │
    └── MISTRAL_API_KEY なし → OpenRouterConfig（シングルモード）
```

### クラス階層

```
OpenRouterConfig
├── api_keys: list[str]      # 複数キー対応
├── model: str
├── rpm_limit: int
├── acquire_key() → (key, wait)  # TokenBucket ベース
└── next_key() → str             # 後方互換

MistralConfig
├── api_key: str
├── model: str
├── rpm_limit: int
└── acquire() → float            # TokenBucket ベース

DualConfig
├── thinker: MistralConfig
├── actor: OpenRouterConfig
└── is_dual: bool (常にTrue)
```

### TokenBucket（utils.py）

各 API キーごとに独立した TokenBucket を作成し、RPM 制限を管理する。

```python
# OpenRouterConfig.__post_init__
self._buckets = [TokenBucket(rpm_limit=self.rpm_limit, rpd_limit=0) for _ in self.api_keys]
```

### PortContext

```python
@dataclass(frozen=True)
class PortContext:
    cwd: Path
    py_file_count: int
    has_tests: bool
    has_config: bool
    top_files: tuple
    py_files: tuple
    cfg_files: tuple
```

作業フォルダのコンテキスト情報を収集し、AI に渡すためのデータ構造。

---

## 6. tools.py — ツールレジストリ

### ToolRegistry

```python
class ToolRegistry:
    def register(name, description, parameters)  # デコレータ
    def get_specs() → list[dict]                  # OpenAI tools 形式
    def copy_tool(name, source) → bool            # 他レジストリからコピー
    def execute(name, args) → Any
```

### 登録済みツール

| ツール名 | 種別 | 説明 |
|----------|------|------|
| `read_file` | 読み取り | 10000文字単位で分割読み取り |
| `read_tool_cache` | 読み取り | キャッシュから続きを読む |
| `get_repo_map` | 読み取り | プロジェクト構造をツリー表示 |
| `list_directory` | 読み取り | ディレクトリ一覧 |
| `glob` | 読み取り | ファイル名パターン検索 |
| `grep` | 読み取り | ripgrep キーワード検索 |
| `write_file` | 書き込み | ファイル作成 |
| `edit_file` | 書き込み | 部分置換編集 |
| `patch_file` | 書き込み | Search&Replace 編集 |
| `append_file` | 書き込み | 末尾追記 |
| `create_directory` | 書き込み | ディレクトリ作成 |
| `move_file` | 書き込み | 移動・リネーム |
| `copy_file` | 書き込み | コピー |
| `delete_file` | 書き込み | 削除 |
| `run_powershell` | 実行 | PowerShell コマンド実行 |
| `web_search` | 検索 | DuckDuckGo Web検索 |
| `fetch_webpage` | 検索 | Webページ取得 |
| `browser_navigate` | ブラウザ | URL遷移 |
| `browser_click` | ブラウザ | 要素クリック |
| `browser_type` | ブラウザ | テキスト入力 |
| `browser_get_text` | ブラウザ | テキスト取得 |
| `browser_screenshot` | ブラウザ | スクリーンショット |
| `browser_close` | ブラウザ | ブラウザ終了 |

### 読み取り履歴チェック

```python
_read_files_registry: set[str] = set()

def _check_read_warning(path: str) -> str:
    # ファイルが現在のターンで read_file されていない場合、警告を返す
```

### 構文チェック

Python ファイル編集後に `py_compile` で構文チェックを実行。

### 書き込み承認フック

```python
_write_approval_handler = None  # Callable[[str, dict, str], bool] | None

def set_write_approval_handler(handler):
    # ReAct モード: 承認ハンドラあり
    # Plan-and-Execute モード: None（承認なし）
```

### キャッシュツール

```python
_CACHEABLE_TOOLS = ["read_file", "list_directory", "search_files", "get_repo_map"]
```

これらのツールは結果がキャッシュされ、同一引数の再呼び出し時に API 経由の再取得をスキップする。

---

## 7. utils.py — ユーティリティ群

### スレッドセーフ出力

```python
_print_lock = threading.Lock()

def safe_print(*args, **kwargs):
    # 複数スレッドからの出力が混ざらないようロック制御
```

### Matrix Green テーマ（C クラス）

ANSI エスケープコードによるカラーテーマ。全色が Green 系統で統一。

| メソッド | 用途 |
|----------|------|
| `C.green()` | メインアクション |
| `C.cyan()` | 観察・ツール結果 |
| `C.purple()` | AI の思考 |
| `C.mem()` | Thinker 出力（Aqua テーマ） |
| `C.yellow()` | 警告・待機 |
| `C.orange()` | 並列処理 |
| `C.red()` | エラー |

### Markdown レンダリング

```python
def render_markdown(text: str) -> str      # Green テーマ（Actor 用）
def render_markdown_thinker(text: str) -> str  # Aqua テーマ（Thinker 用）
```

対応要素: 見出し / 太字 / 斜体 / インラインコード / コードブロック / 箇条書き / 番号リスト / 水平線

### PipelineTypewriter

ストリーミングテキストをバッファ → レンダリング → タイプライター表示する非同期パイプライン。

```python
tw = PipelineTypewriter(renderer=render_markdown_thinker)
tw.start()                              # レンダリングスレッド起動
full_text = stream_call_api(cb=tw.feed) # チャンクを投入
tw.finalize()                           # レンダリング完了を待機
```

### TokenBucket

```python
class TokenBucket:
    def __init__(self, rpm_limit: int, rpd_limit: int)
    def acquire() → tuple[bool, float]  # (成功, 待機秒数)
    def wait_time() → float             # 次のトークン補充までの秒数
```

### ツール出力キャッシュ

```python
_TOOL_CHUNK_SIZE = 10000

def cache_tool_output(tool_name: str, result: str) -> str:
    # 10000文字を超えると自動的にメモリにキャッシュ
    # フッターに cache_key が付与される
```

---

## 8. main.py — 対話ループ

### モード切替

```
/mode interactive  → InteractiveOrchestrator (ReAct)
/mode plan         → AgentOrchestrator (Plan-and-Execute)
/mode dual         → DualModelOrchestrator (Thinker + Actor)
```

### スラッシュコマンド

| コマンド | 説明 |
|----------|------|
| `/mode <mode>` | モード切替 |
| `/undo` | Auto-Git ロールバック |
| `/diff` | バックアップからの差分表示 |
| `/history` | ReAct ログ表示 |
| `/export [path]` | ReAct ログを Markdown で書き出し |
| `/autoexport <分> [path]` | 定期自動エクスポート |
| `/help` | コマンド一覧 |
| `exit` | 終了 |

### パイプモード

```powershell
python -m mimic3 --prompt "質問文"
```

結果を stdout に出力して終了。

### 自動モード

```powershell
python -m mimic3 --auto-prompt "タスク"
```

MCP サーバーから自動実行されるモード。

---

## 9. データフロー図

### Dual モード（フルフロー）

```
ユーザー入力
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ DualModelOrchestrator.run()                              │
│                                                          │
│  1. Thinker.plan(user_message)                           │
│     └→ Mistral API → JSON steps                          │
│                                                          │
│  2. ユーザー承認 (y/N)                                   │
│     └→ 否決: Thinker履歴修正 → 次の入力へ                │
│                                                          │
│  3. _execute_adaptive_workflow(steps, goal)              │
│     ┌──────────────────────────────────────────────┐     │
│     │ for each step:                               │     │
│     │   a. Actor.clear_history()                   │     │
│     │   b. actor_orch.run_react(step.description)  │     │
│     │      └→ ReAct ループ（ツール実行）           │     │
│     │   c. on_failure 処理（retry/skip/abort/goto）│     │
│     │   d. Thinker.step_review() → continue/replan │     │
│     │      └→ replan: remaining を新計画で差し替え │     │
│     │      └→ done: ループ終了                     │     │
│     └──────────────────────────────────────────────┘     │
│                                                          │
│  4. Thinker.review(all_summaries)                        │
│     └→ Mistral API → レビューコメント                    │
│                                                          │
│  5. ユーザーに制御を返す                                  │
└──────────────────────────────────────────────────────────┘
```

### ReAct ループ（InteractiveOrchestrator）

```
user_message
    │
    ▼
AutoGit.backup()
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ ReAct ループ (MAX_REACT_STEPS=60)                        │
│                                                          │
│  AI ストリーミング出力                                   │
│  ┌──────────────────────────────────────────────┐        │
│  │ text_callback → PipelineTypewriter → 表示    │        │
│  └──────────────────────────────────────────────┘        │
│                                                          │
│  ├── tool_calls なし → 最終回答                          │
│  │                                                      │
│  └── tool_calls あり:                                    │
│      ├── 読み取り系のみ → ThreadPoolExecutor 並列実行    │
│      └── 書き込み系含む → 逐次実行 + 承認確認            │
│          ├→ 成功: AutoGit.checkpoint()                   │
│          └→ 拒否: UserRejectedWriteError → ループ停止    │
│                                                          │
│  Observation (role: tool) を messages に追加             │
│  └── ループ先頭へ戻る                                    │
└──────────────────────────────────────────────────────────┘
```

### Plan-and-Execute フロー

```
user_message
    │
    ▼
Planner.run_stream(plan_prompt) → JSON steps
    │
    ▼
_parse_plan() → list[PlanStep]
    │
    ▼
WorkflowGraph(steps)
    │
    ▼
_group_into_batches() → [batch1, batch2, ...]
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ for each batch:                                          │
│   ├── 逐次 (1 step):                                     │
│   │   Executor.run_stream() → result                     │
│   │   Reviewer を非同期投入 (ThreadPoolExecutor)         │
│   │   前ステップの Reviewer 結果を待機                   │
│   │   on_failure → retry/skip/abort/goto                │
│   │   on_success → next/abort/goto                      │
│   │                                                      │
│   └── 並列 (N steps):                                    │
│       ThreadPoolExecutor で同時実行                      │
│       join_policy: all/any/first                         │
│       Reviewer を同期実行 + リトライ                     │
└──────────────────────────────────────────────────────────┘
    │
    ▼
Executor.run_stream(summary_prompt) → final_result
    │
    ▼
_reflect_and_correct() → Reflector 検証 → 修正（必要時）
    │
    ▼
最終結果を返す
```

---

## 付録: 定数一覧

| モジュール | 定数 | 値 | 説明 |
|-----------|------|-----|------|
| `thinker.py` | `MAX_RETRIES` | 4 | Thinker API リトライ上限 |
| `thinker.py` | `BASE_BACKOFF` | 2.0 | バックオフ基本秒数 |
| `thinker.py` | `MAX_BACKOFF` | 30.0 | バックオフ上限秒数 |
| `agent.py` | `MAX_RETRIES` | 5 | Actor API リトライ上限 |
| `agent.py` | `BASE_BACKOFF` | 2.0 | バックオフ基本秒数 |
| `agent.py` | `MAX_BACKOFF` | 60.0 | バックオフ上限秒数 |
| `agent.py` | `MAX_TOOL_ROUNDS` | 60 | ReAct ループ上限 |
| `orchestrator.py` | `MAX_STEP_RETRY` | 2 | 1ステップあたりのリトライ上限 |
| `orchestrator.py` | `GOTO_HARD_LIMIT` | 10 | goto ループの安全上限 |
| `orchestrator.py` | `MAX_AUTO_RETRY` | 2 | ReAct エラー自動リトライ上限 |
| `orchestrator.py` | `MAX_REACT_STEPS` | 60 | ReAct ループ上限 |
| `orchestrator.py` | `MAX_REPLAN_COUNT` | 3 | 再計画の上限回数 |
| `orchestrator.py` | `_THINKER_COOLDOWN` | 40秒 | Thinker 冷却時間 |
| `agent.py` | `COMPACTION_THRESHOLD_CHARS` | 3,000,000 | コンテキスト圧縮閾値 |
| `agent.py` | `COMPACTION_KEEP_RECENT` | 20 | 圧縮時に保持する直近メッセージ数 |
| `tools.py` | `_READ_FILE_CHAR_CHUNK` | 10,000 | read_file のチャンクサイズ |
| `utils.py` | `_TOOL_CHUNK_SIZE` | 10,000 | ツール出力キャッシュのチャンクサイズ |
