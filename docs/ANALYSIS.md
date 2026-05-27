# Mimic3 独自実装 技術資料

> **バージョン**: Mimic3 (tamalabo フォーク)  
> **ベース**: V4.py を split_v4.py でモジュール分割  
> **開発者**: Loser1025 (https://github.com/Loser1025/mimic)  
> **作成日**: 2025年  

---

## 目次

1. [プロジェクト概要](#1-プロジェクト概要)
2. [GitHub版（V4）との差分分析](#2-github版v4との差分分析)
3. [独自実装部分の技術仕様](#3-独自実装部分の技術仕様)
4. [依存ライブラリの更新状況](#4-依存ライブラリの更新状況)
5. [今後の更新戦略](#5-今後の更新戦略)

---

## 1. プロジェクト概要

### 1.1 開発者情報

| 項目 | 内容 |
|------|------|
| **開発者** | Loser1025 |
| **リポジトリ** | https://github.com/Loser1025/mimic |
| **ベースコード** | V4.py（単一ファイルの統合エージェント） |
| **モジュール分割ツール** | split_v4.py（V4.py → 10モジュールに自動分割） |
| **ライセンス** | 明記なし（個人プロジェクト） |

### 1.2 独自バージョンの位置づけ

Mimic3 は、V4.py と呼ばれる単一ファイルの AI エージェントを **モジュール分割・機能拡張** した独自フォークである。

**V4.py（オリジナル）の特徴:**
- 単一ファイル（約 90,000 行）の統合 AI エージェント
- Gemini API ベースの ReAct ループ
- ファイル操作・PowerShell 実行・Web 検索を自律実行

**Mimic3（本プロジェクト）の独自性:**

```
V4.py（単一ファイル・Gemini）
    │
    │  split_v4.py によるモジュール分割
    │  Gemini → OpenRouter/OwlAlpha に変更
    │  Mistral Thinker 追加
    │  デュアルモデル対応
    │  MCP サーバー対応
    ▼
Mimic3（マルチモジュール・デュアルモデル）
```

| 観点 | V4.py（原版） | Mimic3（独自版） |
|------|---------------|-----------------|
| **ファイル構成** | 単一ファイル | 10モジュールに分割 |
| **AI モデル** | Gemini（Google） | OpenRouter/OwlAlpha（Actor）+ Mistral Large 3（Thinker） |
| **アーキテクチャ** | 単一エージェント ReAct | 最大3層マルチエージェント |
| **実行モード** | ReAct のみ | ReAct / Plan-and-Execute / Dual（3モード） |
| **MCP 連携** | なし | MCP サーバー対応（Claude Code 連携） |
| **レート制限** | 簡易 | Token Bucket アルゴリズム（RPM/RPD） |
| **Auto-Git** | なし | 自動バックアップ・チェックポイント・ロールバック |
| **コンテキスト管理** | なし | 自動コンパクション + メッセージ修復 |

---

## 2. GitHub版（V4）との差分分析

### 2.1 追加機能一覧

#### 2.1.1 デュアルモデルアーキテクト（DualModelOrchestrator）

V4 には存在しない最大の追加機能。Mistral Large 3 を「テックリード（Thinker）」、OwlAlpha を「実行者（Actor）」として分離した2モデル構成。

```
V4:   ユーザー → Gemini（思考+実行）→ 結果
Mimic3: ユーザー → Mistral（計画）→ OwlAlpha（実行）→ Mistral（評価）→ 結果
```

| 機能 | V4 | Mimic3 |
|------|----|--------|
| Thinker（計画AI） | なし | Mistral Large 3 |
| Actor（実行AI） | Gemini | OpenRouter/OwlAlpha |
| ステップ評価 | なし | Thinker.step_review() |
| 動的再計画 | なし | replan 対応（MAX_REPLAN_COUNT=3） |
| 冷却タイマー | なし | 40秒間隔の Thinker 呼び出し制限 |

#### 2.1.2 Plan-and-Execute オーケストレーター

V4 の ReAct ループを拡張し、Planner → Executor → Reviewer の3エージェント協業を実現。

| コンポーネント | V4 | Mimic3 |
|---------------|----|--------|
| Planner | なし | JSON 計画生成（ツールなし） |
| Executor | メイン ReAct | ツール実行特化 |
| Reviewer | なし | ステップ結果検証 |
| Reflector | なし | 最終結果の自己検証 |
| 並列実行 | なし | ThreadPoolExecutor バッチ化 |
| ワークフロー制御 | なし | WorkflowGraph（goto/retry/skip/abort） |

#### 2.1.3 WorkflowGraph

V4 にはない、グラフベースのワークフロー制御エンジン。

| 機能 | V4 | Mimic3 |
|------|----|--------|
| 条件分岐 | なし | on_success / on_failure |
| goto ジャンプ | なし | ラベルベースのジャンプ |
| ループ防止 | なし | max_iterations + GOTO_HARD_LIMIT=10 |
| 共有ステート | なし | [STATE: key=value] 自動パース |
| 並列バッチ | なし | join_policy（all/any/first） |

#### 2.1.4 Auto-Git システム

V4 にはない、タスク実行時の安全ネット機能。

| 機能 | V4 | Mimic3 |
|------|----|--------|
| タスク前バックアップ | なし | git init + 自動コミット |
| 書き込み後チェックポイント | なし | ツール成功時に自動コミット |
| ロールバック | なし | /undo コマンドで即座に復元 |
| 差分表示 | なし | /diff コマンド |

#### 2.1.5 MCP サーバー対応

V4 にはない、Claude Code との MCP 連携。

| 機能 | V4 | Mimic3 |
|------|----|--------|
| MCP サーバー | なし | mcp_server.py（stdio 通信） |
| agent_run ツール | なし | フルエージェント実行 |
| agent_terminal ツール | なし | インタラクティブ起動 |
| ログ監視 | なし | PowerShell ウィンドウ自動起動 |

#### 2.1.6 レート制限の高度化

| 機能 | V4 | Mimic3 |
|------|----|--------|
| アルゴリズム | 簡易カウント | Token Bucket |
| RPM 制御 | なし | キーごとに独立バケット |
| RPD 制御 | なし | 日次カウンタ（無制限モード対応） |
| 複数キー | なし | 最大9キー対応（round-robin） |

#### 2.1.7 コンテキスト管理の高度化

| 機能 | V4 | Mimic3 |
|------|----|--------|
| 自動コンパクション | なし | 300万文字閾値で圧縮 |
| メッセージ修復 | なし | 孤立 tool_calls 除去 |
| メッセージトリム | なし | 古い tool メッセージ優先削除 |
| ツール出力キャッシュ | なし | 10000文字超で自動キャッシュ |

#### 2.1.8 スラッシュコマンドの拡張

| コマンド | V4 | Mimic3 |
|----------|----|--------|
| /mode | なし | interactive/plan/dual 切替 |
| /undo | なし | Auto-Git ロールバック |
| /diff | なし | バックアップからの差分 |
| /history | なし | ReAct ログ表示 |
| /export | なし | Markdown エクスポート |
| /autoexport | なし | 定期自動エクスポート |
| /think | なし | 推論モード切替 |
| /task | なし | タスクゴール管理 |

### 2.2 削除・変更された機能

| 項目 | V4 | Mimic3 |
|------|----|--------|
| **AI プロバイダ** | Gemini（Google） | OpenRouter（OwlAlpha） |
| **API 通信** | Google API SDK | urllib（標準ライブラリのみ） |
| **Wikipedia ツール** | あり | 削除 |
| **RAG 機能** | あり（RAG ドキュメント参照） | 削除 |
| **教訓保存** | あり（lessons.json） | 削除 |
| **対話型プロンプト** | あり | 削除（MCP に委譲） |

---

## 3. 独自実装部分の技術仕様

### 3.1 DualModelOrchestrator

#### クラス構成

```python
class DualModelOrchestrator:
    def __init__(self, thinker: MistralThinker, 
                 actor_orch: InteractiveOrchestrator, 
                 auto_git: AutoGit)
```

#### 実行フロー

```
ユーザー入力
    │
    ▼
[1] Thinker.plan(user_message)
    └→ Mistral API → JSON steps
    │
    ▼
[2] ユーザー承認 (y/N)
    └→ 否決: Thinker履歴修正 → 次の入力へ
    │
    ▼
[3] _execute_adaptive_workflow(steps, goal)
    ┌──────────────────────────────────────────────┐
    │ for each step:                               │
    │   a. Actor.clear_history()                   │
    │   b. actor_orch.run_react(step.description)  │
    │   c. Thinker.step_review() → continue/replan │
    │      └→ replan: remaining を新計画で差し替え │
    │      └→ done: ループ終了                     │
    └──────────────────────────────────────────────┘
    │
    ▼
[4] Thinker.review(all_summaries)
    └→ Mistral API → レビューコメント
    │
    ▼
[5] ユーザーに制御を返す
```

#### 主要定数

| 定数 | 値 | 説明 |
|------|-----|------|
| `MAX_STEP_RETRY` | 2 | 1ステップあたりの最大リトライ回数 |
| `MAX_REPLAN_COUNT` | 3 | 再計画の上限回数 |
| `_THINKER_COOLDOWN` | 40秒 | Thinker 連続呼び出し防止の冷却時間 |

### 3.2 MistralThinker

#### クラス構成

```python
class MistralThinker:
    def __init__(self, config: MistralConfig, 
                 base_system_prompt: str = "")
```

#### 主要メソッド

| メソッド | 戻り値 | 説明 |
|----------|--------|------|
| `think(user_message)` | `str` | Actor への詳細指示書を生成 |
| `plan(user_message)` | `list[dict]` | ユーザータスクを PlanStep リストに分解 |
| `review(actor_summary)` | `str` | Actor の実行結果をレビュー |
| `step_review(...)` | `dict` | 1ステップ実行後に評価・再計画 |

#### step_review の戻り値

```python
{"action": "continue", "reason": "..."}                    # 続行
{"action": "replan", "reason": "...", "steps": [...]}     # 再計画
{"action": "done", "reason": "..."}                        # 完了
```

#### JSON パイプライン

Mistral の出力から JSON を抽出する共通パイプライン:

1. コードブロック（` ```json ... ``` `）を剥がす
2. `command` / `content` / `code` フィールドを除去
3. Brace-matching で全 `{ ... }` ブロックを列挙
4. `json.loads` が成功し、必要なキーを持つ最初のブロックを採用

#### エラーハンドリング

| 例外 | 説明 |
|------|------|
| `MistralAPIError` | HTTP エラー（status, message を持つ） |
| `MistralRateLimitError` | 429 レート制限（サブクラス） |

リトライ: 最大 `MAX_RETRIES=4` 回、指数バックオフ（`BASE_BACKOFF=2.0`, `MAX_BACKOFF=30.0`）

### 3.3 WorkflowGraph

#### PlanStep データクラス

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

#### 共有ステート

```python
graph.state_set("api_key", "abc123")          # キー/値保存
graph.state_get("api_key")                     # → "abc123"
graph.parse_state_updates(result)              # [STATE: key=value] を自動パース
```

### 3.4 AgentOrchestrator（Plan-and-Execute）

#### 3エージェント構成

```
Planner (JSON計画) → Executor (ツール実行) → Reviewer (結果検証)
                                              ↓
                                         Reflector (最終検証)
```

#### 実行フロー

1. **Planner** がタスクをステップに分解（JSON）
2. **WorkflowGraph** を構築
3. ステップをバッチ化（連続する `parallel=True` をグループ化）
4. 逐次ステップ: Reviewer を **非同期投入**（次のステップとオーバーラップ実行）
5. 並列ステップ: `ThreadPoolExecutor` で同時実行
6. 全ステップ完了後、**Reflection Loop** で最終検証

#### 並列バッチ制御

```python
[F, T, T, F] → [[F], [T, T], [F]]
```

| `join_policy` | 動作 |
|---------------|------|
| `"all"` | 全並列ステップの完了を待つ（デフォルト） |
| `"any"` | いずれか1つが成功した時点で残りをスキップ |
| `"first"` | 成功/失敗を問わず最初に完了した結果で次へ進む |

### 3.5 InteractiveOrchestrator（ReAct）

#### ReAct ループ

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

#### ツールキャッシュ

- 読み取り系ツール（`read_file`, `list_directory`, `search_files`, `get_repo_map`）の結果をキャッシュ
- 書き込み系ツール実行後、関連するキャッシュを自動無効化

### 3.6 OpenRouterAgent

#### コンテキスト圧縮

```python
COMPACTION_THRESHOLD_CHARS = 3_000_000  # 約75%のコンテキスト使用率で発動
COMPACTION_KEEP_RECENT = 20             # 直近20メッセージを保持
```

#### メッセージ修復

`_repair_message_sequence()` が OpenAI ネイティブ形式の整合性を保証:
- 孤立した `tool_calls` を除去
- 孤立した `role:tool` を除去
- `assistant+tool_calls` → `tool` の対応関係を検証

#### リトライ戦略

| エラー | 動作 |
|--------|------|
| 429 RateLimitError | 指数バックオフ + ジッター |
| 5xx ServerError | バックオフ + メッセージトリム |
| 接続エラー | バックオフ + リトライ |
| その他 API エラー | 即座に例外送出 |

リトライ上限: `MAX_RETRIES=5`、`BASE_BACKOFF=2.0`、`MAX_BACKOFF=60.0`

### 3.7 Token Bucket レートリミッター

```python
class TokenBucket:
    def __init__(self, rpm_limit: int = 15, rpd_limit: int = 1500):
```

**アルゴリズム:**
- バケツ容量 = `rpm_limit` トークン
- 補充レート = `rpm_limit / 60` トークン/秒
- リクエストごとに 1 トークンを消費
- RPD 無制限モード対応（`rpd_limit=0`）
- スレッドセーフ（`threading.Lock` による排他制御）

### 3.8 PipelineTypewriter

AI ストリーミングを3段パイプラインで表示:

```
Stage1: rawバッファに蓄積（改行 or 200文字超で区切り）
Stage2: render_markdown でレンダリング（完全行のみ）
Stage3: タイプライタースレッドが1文字ずつ出力（500文字/秒）
```

コードブロックが途中の場合は閉じるまでバッファを保持する。

### 3.9 ツールレジストリ

#### 登録済みツール（23種）

| カテゴリ | ツール名 |
|----------|----------|
| **読み取り** | `read_file`, `read_tool_cache`, `get_repo_map`, `list_directory`, `glob`, `grep` |
| **書き込み** | `write_file`, `edit_file`, `patch_file`, `append_file`, `create_directory`, `move_file`, `copy_file`, `delete_file` |
| **実行** | `run_powershell` |
| **検索** | `web_search`, `fetch_webpage` |
| **ブラウザ** | `browser_navigate`, `browser_click`, `browser_type`, `browser_get_text`, `browser_screenshot`, `browser_close` |

#### 読み取り履歴チェック

```python
_read_files_registry: set[str] = set()

def _check_read_warning(path: str) -> str:
    # ファイルが現在のターンで read_file されていない場合、警告を返す
```

#### 構文チェック

Python ファイル編集後に `py_compile` で構文チェックを実行。

### 3.10 MCP サーバー

#### 提供ツール

| ツール名 | 説明 |
|----------|------|
| `agent_run` | フルエージェント実行（ReAct ループ + AutoGit） |
| `agent_terminal` | インタラクティブモードでターミナル起動 |

#### 通信方式

- MCP stdio プロトコル
- Claude Code の `settings.json` から起動
- `MIMIC_CWD` 環境変数で作業ディレクトリを指定

---

## 4. 依存ライブラリの更新状況

### 4.1 現在の依存関係

#### 標準ライブラリのみ（追加インストール不要）

| モジュール | 使用箇所 |
|------------|----------|
| `urllib.request` | API 通信（OpenRouter, Mistral） |
| `http.client` | 接続エラーハンドリング |
| `json` | シリアライズ/デシリアライズ |
| `threading` | 並列実行・ロック制御 |
| `concurrent.futures` | ThreadPoolExecutor |
| `subprocess` | PowerShell 実行 |
| `tempfile` | 一時ファイル |
| `pathlib` | パス操作 |
| `dataclasses` | データクラス |
| `ast` | Python 構文解析 |
| `difflib` | 差分生成 |
| `re` | 正規表現 |
| `logging` | ログ出力 |
| `collections` | deque |
| `uuid` | ツール呼び出し ID 生成 |
| `base64` | MCP サーバー（EncodedCommand） |
| `asyncio` | MCP サーバー |
| `io` | エンコーディング |
| `os` | 環境変数 |
| `sys` | システム操作 |
| `time` | 待機・タイムスタンプ |
| `math` | 計算 |
| `fnmatch` | glob パターン |
| `datetime` | 日時処理 |

#### 外部ライブラリ

| ライブラリ | バージョン | 用途 | 必須 |
|------------|------------|------|------|
| `mcp` | 最新 | MCP サーバー通信 | △ MCP 使用時のみ |
| `playwright` | 最新 | ブラウザ操作 | △ ブラウザ使用時のみ |

### 4.2 V4 からの変更点

| ライブラリ | V4 | Mimic3 |
|------------|----|--------|
| `google-generativeai` | 必須 | **削除** |
| `requests` | 使用 | **削除**（urllib に変更） |
| `mcp` | なし | **追加** |
| `playwright` | なし | **追加** |

### 4.3 軽量化の効果

V4 では `google-generativeai` SDK と `requests` が必要だったが、Mimic3 では標準ライブラリの `urllib` に置き換えたことで、**通常運用時は追加インストールが不要**になった。

```bash
# V4 の依存
pip install google-generativeai requests

# Mimic3 の依存（通常運用時）
# 追加インストール不要

# MCP サーバー使用時のみ
pip install mcp

# ブラウザ操作使用時のみ
pip install playwright
playwright install
```

---

## 5. 今後の更新戦略

### 5.1 独自機能の維持方法

#### 5.1.1 モジュール構造の維持

現在の10モジュール構成を維持し、機能追加は既存モジュール内で行う。

```
mimic3/
├── __init__.py      # パッケージ初期化
├── __main__.py      # エントリポイント
├── main.py          # 対話ループ・モード切替
├── agent.py         # OpenRouterAgent（ReAct ループ）
├── thinker.py       # MistralThinker（テックリード）
├── orchestrator.py  # 4種のオーケストレーター
├── config.py        # 設定管理
├── tools.py         # ツールレジストリ
├── autogit.py       # Auto-Git システム
├── commands.py      # スラッシュコマンド
├── mcp_server.py    # MCP サーバー
├── utils.py         # ユーティリティ
└── SPEC.md          # 仕様書
```

#### 5.1.2 設定ファイルの管理

`.env` ファイルで API キーとモデル設定を管理。テンプレート自動生成機能により、新規セットアップが容易。

```env
# Thinker 設定
MISTRAL_API_KEY=your_key
MISTRAL_MODEL=mistral-large-latest
MISTRAL_RPM_LIMIT=2

# Actor 設定
OPENROUTER_KEY_1=your_key_1
OPENROUTER_KEY_2=your_key_2
OPENROUTER_KEY_3=your_key_3
OPENROUTER_MODEL=openrouter/owl-alpha
RPM_LIMIT=4
```

#### 5.1.3 テスト戦略

`test_keys.py` による API キーの健全性チェックを維持。

```bash
python -m mimic3.test_keys
```

### 5.2 機能拡張のロードマップ

#### 短期（1-3ヶ月）

| 優先度 | 機能 | 説明 |
|--------|------|------|
| 高 | モデル追加 | 新しい無料モデル（Gemma 3, DeepSeek V3 等）のサポート |
| 高 | エラーハンドリング強化 | Thinker の JSON パース失敗時の復旧力向上 |
| 中 | パフォーマンス最適化 | ツールキャッシュの効率化 |
| 中 | ドキュメント整備 | SPEC.md の継続的更新 |

#### 中期（3-6ヶ月）

| 優先度 | 機能 | 説明 |
|--------|------|------|
| 高 | マルチモデルの動的切替 | タスクに応じた最適モデル自動選択 |
| 中 | プラグインシステム | 外部ツールの動的ロード |
| 中 | Web UI | ブラウザベースの管理画面 |
| 低 | 分散実行 | 複数マシンでの並列実行 |

#### 長期（6ヶ月以上）

| 優先度 | 機能 | 説明 |
|--------|------|------|
| 中 | 自律学習 | 実行結果からの自動改善 |
| 低 | マルチモーダル | 画像・音声入力のサポート |
| 低 | チーム協調 | 複数エージェントの協調作業 |

### 5.3 互換性維持のための注意点

#### 5.3.1 API 互換性

- OpenRouter API は OpenAI 互換フォーマットを採用。API 仕様変更時は `_call_openrouter_api()` と `_stream_openrouter_api()` のみ修正すればよい。
- Mistral API も OpenAI 互換。同様に `_call_api()` と `_stream_call_api()` を修正。

#### 5.3.2 モデル変更時の影響範囲

| 変更箇所 | 影響を受けるモジュール |
|----------|------------------------|
| Actor モデル変更 | `config.py`, `agent.py` |
| Thinker モデル変更 | `config.py`, `thinker.py` |
| システムプロンプト変更 | `config.py`, `main.py` |
| ツール追加 | `tools.py`, `orchestrator.py` |

#### 5.3.3 バージョン管理

Auto-Git システムにより、すべての変更は自動的に Git で追跡される。問題が発生した場合は `/undo` で即座に復元可能。

```bash
# ロールバック
/undo

# 差分確認
/diff
```

### 5.4 セキュリティ考慮事項

| 項目 | 対策 |
|------|------|
| API キー管理 | `.env` ファイル（.gitignore で除外） |
| 書き込み承認 | ReAct モードでのユーザー確認 |
| 自動バックアップ | Auto-Git による変更追跡 |
| 構文チェック | Python ファイル編集後の自動検証 |
| ツール実行制限 | ホワイトリスト方式（登録ツールのみ実行可能） |

---

## 付録

### A. ファイル構成と行数

| ファイル | 行数 | 概要 |
|----------|------|------|
| `orchestrator.py` | ~1,800 | 4種のオーケストレーター |
| `agent.py` | ~650 | OpenRouterAgent |
| `thinker.py` | ~500 | MistralThinker |
| `tools.py` | ~1,000 | ツールレジストリ（23ツール） |
| `utils.py` | ~450 | ユーティリティ |
| `config.py` | ~260 | 設定管理 |
| `main.py` | ~320 | 対話ループ |
| `autogit.py` | ~280 | Auto-Git |
| `commands.py` | ~110 | スラッシュコマンド |
| `mcp_server.py` | ~220 | MCP サーバー |
| `SPEC.md` | ~570 | 仕様書 |
| **合計** | **~6,160** | |

### B. 用語集

| 用語 | 説明 |
|------|------|
| **ReAct** | Reason + Act の略。AI が思考→実行→観察を繰り返すパターン |
| **Thinker** | Mistral Large 3 を使用する計画・評価専用 AI |
| **Actor** | OwlAlpha を使用する実行専用 AI |
| **Planner** | タスクをステップに分解する AI |
| **Executor** | ステップをツールで実行する AI |
| **Reviewer** | 実行結果を検証する AI |
| **Reflector** | 最終結果を自己検証する AI |
| **Token Bucket** | レート制限のアルゴリズム |
| **WorkflowGraph** | グラフベースのワークフロー制御 |
| **Auto-Git** | 自動 Git バックアップ・ロールバック |
| **MCP** | Model Context Protocol。AI と外部ツールの通信プロトコル |

---

*本資料は Mimic3 プロジェクトのコードベースを基に作成された。*
