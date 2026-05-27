# Mimic3 システムアーキテクチャ

## 1. 全体アーキテクチャ（Mermaid）

```mermaid
graph TB
    subgraph Entry["エントリポイント"]
        MAIN["__main__.py<br/>main()"]
        MCP["mcp_server.py<br/>MCP Server"]
    end

    subgraph Config["設定層"]
        ENV[".env ファイル"]
        CFG["config.py<br/>load_config()"]
        DCFG["DualConfig<br/>(Thinker + Actor)"]
        OCFG["OpenRouterConfig<br/>(Actor 単体)"]
    end

    subgraph Orchestrator["オーケストレーション層"]
        DMO["DualModelOrchestrator"]
        AO["AgentOrchestrator<br/>(Plan-and-Execute)"]
        IO["InteractiveOrchestrator<br/>(ReAct)"]
        WG["WorkflowGraph<br/>(状態機械)"]
    end

    subgraph AI["AI モデル層"]
        THINKER["MistralThinker<br/>(Mistral Large 3)<br/>ツール呼び出しなし"]
        ACTOR["OpenRouterAgent<br/>(OwlAlpha)<br/>フルツール使用"]
        PLANNER["Planner<br/>(OpenRouter + JSON mode)"]
        REVIEWER["Reviewer<br/>(OpenRouter)"]
        REFLECTOR["Reflector<br/>(OpenRouter)"]
    end

    subgraph Tools["ツール層"]
        TR["ToolRegistry"]
        PS["run_powershell"]
        RF["read_file / write_file<br/>edit_file / patch_file"]
        WEB["web_search<br/>fetch_webpage"]
        FS["list_directory<br/>glob / search_files<br/>get_repo_map"]
    end

    subgraph Infra["インフラ層"]
        AG["AutoGit<br/>自動バックアップ"]
        TL["TokenBucket<br/>レート制限"]
        RL["ReactLog<br/>会話ログ"]
    end

    MAIN --> CFG
    MCP --> MAIN
    ENV --> CFG
    CFG --> DCFG
    CFG --> OCFG

    MAIN --> DMO
    MAIN --> AO
    MAIN --> IO
    DMO --> THINKER
    DMO --> IO
    DMO --> AG
    IO --> ACTOR
    AO --> PLANNER
    AO --> REVIEWER
    AO --> REFLECTOR
    AO --> WG
    AO --> ACTOR

    ACTOR --> TR
    TR --> PS
    TR --> RF
    TR --> WEB
    TR --> FS

    ACTOR --> TL
    ACTOR --> AG
    IO --> RL
    DMO --> AG
```

## 2. 3つの実行モード

```mermaid
graph LR
    USER["ユーザー入力"] --> MODE{モード選択}

    MODE -->|dual| DUAL["Dual モード<br/>Thinker + Actor"]
    MODE -->|interactive| REACT["Interactive モード<br/>ReAct ループ"]
    MODE -->|plan| PLAN["Plan モード<br/>Plan-and-Execute"]

    DUAL --> RESULT["最終結果"]
    REACT --> RESULT
    PLAN --> RESULT
```

## 3. DualModelOrchestrator 協調ロジック（シーケンス図）

```mermaid
sequenceDiagram
    autonumber
    participant U as ユーザー
    participant DMO as DualModelOrchestrator
    participant MT as MistralThinker
    participant IO as InteractiveOrchestrator
    participant OA as OpenRouterActor
    participant AG as AutoGit
    participant WG as WorkflowGraph

    U->>DMO: run(user_message)

    rect rgb(173, 216, 230)
        Note over DMO,MT: Phase 1: 計画生成
        DMO->>MT: plan(user_message)
        MT-->>DMO: steps JSON
        DMO->>U: 計画表示 (Step 1..N)
        U->>DMO: 承認 [y/N]
    end

    rect rgb(144, 238, 144)
        Note over DMO,OA,MT: Phase 2: 適応型ワークフロー実行
        loop 各ステップ (remaining が空になるまで)
            DMO->>OA: run_react(step.description)
            OA->>AG: backup(cwd)
            OA-->>DMO: step_result
            DMO->>WG: parse_state_updates(result)

            alt ステップ失敗
                DMO->>WG: resolve_failure()
                alt retry
                    DMO->>OA: 再実行
                alt skip
                    Note over DMO: 次ステップへ
                alt abort
                    DMO-->>U: 中断
                alt goto:label
                    DMO->>DMO: ジャンプ先へ
                end
            end

            alt ステップ成功
                DMO->>WG: resolve_success()
                alt goto:label
                    DMO->>DMO: ジャンプ先へ
                end
            end

            rect rgb(255, 255, 224)
                Note over DMO,MT: Thinker ステップ評価
                DMO->>MT: step_review(goal, executed, result, remaining)
                MT-->>DMO: decision JSON
                alt action=continue
                    Note over DMO: 残りをそのまま続行
                alt action=replan
                    DMO->>MT: 新計画で remaining を差し替え
                    Note over DMO: replan_count++
                alt action=done
                    DMO->>DMO: ループ終了
                end
            end
        end
    end

    rect rgb(255, 228, 225)
        Note over DMO,MT: Phase 3: 最終レビュー
        DMO->>MT: review(all_summaries)
        MT-->>DMO: レビューコメント
        DMO-->>U: 結果表示
    end
```

## 4. Thinker ↔ Actor 協調の詳細フロー

```mermaid
stateDiagram-v2
    [*] --> ThinkerPlan: ユーザー入力

    ThinkerPlan: Thinker が計画生成
    state ThinkerPlan {
        [*] --> PlanJSON
        PlanJSON: JSON ステップ生成
        PlanJSON --> UserApproval
        UserApproval: ユーザー承認
    }

    ThinkerPlan --> AdaptiveLoop: 承認後

    AdaptiveLoop: 適応型ループ
    state AdaptiveLoop {
        [*] --> ActorExecute
        ActorExecute: Actor がステップ実行
        ActorExecute --> StepEval
        StepEval: Thinker がステップ評価

        state StepEval {
            [*] --> Decision
            Decision: action 判定
            Decision --> Continue: continue
            Decision --> Replan: replan
            Decision --> Done: done
        }

        StepEval --> ActorExecute: continue
        StepEval --> ReplanSteps: replan
        ReplanSteps: 残りステップ差し替え
        ReplanSteps --> ActorExecute
    }

    AdaptiveLoop --> ThinkerReview: 全ステップ完了

    ThinkerReview: Thinker が最終レビュー
    state ThinkerReview {
        [*] --> ReviewOutput
        ReviewOutput: 完了報告・課題・推奨
    }

    ThinkerReview --> [*]: ユーザーへ結果
```

## 5. WorkflowGraph 状態遷移

```mermaid
stateDiagram-v2
    direction LR

    state "PlanStep 状態" as PS {
        [*] --> pending
        pending --> running: 実行開始
        running --> done: 成功
        running --> failed: 失敗
        failed --> retrying: retry
        retrying --> running: 再実行
        retrying --> skipped: 上限超過
        failed --> skipped: skip
    }

    state "エッジ解決" as ER {
        state "on_failure" as OF {
            [*] --> retry
            [*] --> skip
            [*] --> abort
            [*] --> goto
        }
        state "on_success" as OS {
            [*] --> next
            [*] --> abort
            [*] --> goto
        }
    }
```

## 6. ReAct ループ（InteractiveOrchestrator）

```mermaid
flowchart TD
    START["run_react(user_message)"] --> BACKUP["AutoGit.backup()"]
    BUILD["コンテキスト構築"] --> LOOP{"ReAct ループ<br/>max 60 steps"}

    BACKUP --> BUILD

    LOOP --> STREAM["ストリーミング API 呼び出し"]
    STREAM --> HAS_TOOL{"ツール呼び出し<br/>あり?"}

    HAS_TOOL -->|なし| FINAL["最終回答<br/>→ 会話履歴保存 → 返却"]
    HAS_TOOL -->|あり| PARALLEL{"読み取りのみ<br/>複数?"}

    PARALLEL -->|はい| PAR_EXEC["並列ツール実行<br/>ThreadPoolExecutor"]
    PARALLEL -->|いいえ| SEQ_EXEC["逐次ツール実行<br/>+ AutoGit checkpoint"]

    PAR_EXEC --> OBS["Observation を<br/>messages に追加"]
    SEQ_EXEC --> OBS

    OBS --> LOOP

    FINAL --> END["終了"]
```

## 7. Plan-and-Execute ループ（AgentOrchestrator）

```mermaid
flowchart TD
    START["run_with_plan()"] --> PLAN["Planner: ステップ生成"]
    PLAN --> BATCH["バッチグループ化<br/>parallel=T/F で分割"]

    BATCH --> EXEC_LOOP{"バッチループ"}
    EXEC_LOOP --> SEQUENTIAL{"逐次バッチ?"}
    SEQUENTIAL -->|はい| SEQ["逐次実行<br/>+ Reviewer 非同期投入"]
    SEQUENTIAL -->|いいえ| PAR["並列実行<br/>ThreadPoolExecutor"]

    SEQ --> REVIEWER_FUTURE["Reviewer Future<br/>次のバッチ前に結果収集"]
    PAR --> NEXT_BATCH

    REVIEWER_FUTURE --> HANDLE{"Reviewer 結果"}
    HANDLE -->|ok| NEXT_BATCH
    HANDLE -->|fail| RETRY{"リトライ<br/>可能?"}
    RETRY -->|はい| SEQ
    RETRY -->|いいえ| NEXT_BATCH

    NEXT_BATCH --> EXEC_LOOP

    EXEC_LOOP -->|全バッチ完了| SUMMARY["最終まとめ生成"]
    SUMMARY --> REFLECT["Reflector: 最終検証"]
    REFLECT -->|問題あり| CORRECT["Executor で修正"]
    REFLECT -->|OK| RESULT["結果返却"]
    CORRECT --> RESULT
```

## 8. データフロー全体像

```mermaid
flowchart LR
    subgraph Input["入力層"]
        CLI["CLI 引数<br/>--prompt / --auto-prompt"]
        STDIN["対話入力<br/>stdin"]
        MCP_IN["MCP ツール呼び出し<br/>agent_run"]
    end

    subgraph Core["コア処理"]
        CFG["config.py<br/>環境設定ロード"]
        ROUTER["モード分岐<br/>dual / interactive / plan"]
        DUAL["DualModelOrchestrator"]
        REACT["InteractiveOrchestrator"]
        PLAN["AgentOrchestrator"]
    end

    subgraph Models["AI モデル"]
        MISTRAL["Mistral Large 3<br/>Thinker"]
        OPENROUTER["OpenRouter<br/>OwlAlpha Actor"]
    end

    subgraph Output["出力層"]
        STDOUT["stdout 出力"]
        LOG["mimic.log"]
        REACT_LOG["react_log.md"]
        GIT["AutoGit コミット"]
    end

    CLI --> CFG
    STDIN --> ROUTER
    MCP_IN --> CFG

    CFG --> ROUTER
    ROUTER --> DUAL
    ROUTER --> REACT
    ROUTER --> PLAN

    DUAL --> MISTRAL
    DUAL --> REACT
    REACT --> OPENROUTER
    PLAN --> OPENROUTER

    MISTRAL --> STDOUT
    OPENROUTER --> STDOUT
    OPENROUTER --> LOG
    REACT --> REACT_LOG
    DUAL --> GIT
    REACT --> GIT
```

## 9. クラス関係図

```mermaid
classDiagram
    class DualModelOrchestrator {
        +MistralThinker thinker
        +InteractiveOrchestrator actor_orch
        +AutoGit auto_git
        +run(user_message) str
        -_execute_adaptive_workflow(steps, goal) str
        -_execute_workflow_plan(steps) str
        -_wait_cooldown()
    }

    class MistralThinker {
        +MistralConfig config
        +conversation history
        +think(user_message) str
        +plan(user_message) list
        +review(summary) str
        +step_review(goal, executed, result, remaining) dict
        -_call_api(messages) str
        -_stream_call_api(messages, callback) str
    }

    class InteractiveOrchestrator {
        +OpenRouterAgent agent
        +AutoGit auto_git
        +ReactLog react_log
        +run_react(user_message) str
        -_run_react_inner(user_message) str
        -_execute_with_intervention(name, args) str
    }

    class AgentOrchestrator {
        +OpenRouterAgent planner
        +OpenRouterAgent executor
        +OpenRouterAgent reflector
        +run_with_plan(user_message) str
        -_parse_plan(text) list
        -_execute_step(step, agent) str
        -_reflect_and_correct(goal, result) str
    }

    class WorkflowGraph {
        +list~PlanStep~ steps
        +dict state
        +resolve_failure(step) tuple
        +resolve_success(step) tuple
        +parse_state_updates(result)
        +state_set(key, value)
    }

    class PlanStep {
        +int index
        +str description
        +str status
        +str result
        +bool parallel
        +str label
        +str on_failure
        +str on_success
        +int max_iterations
        +str join_policy
    }

    class OpenRouterAgent {
        +AccountRotator rotator
        +ToolRegistry tools
        +str cwd
        +run(prompt) str
        +run_stream(prompt, callback) str
        +set_system_prompt(prompt)
        +clear_history()
        -_stream_react_call(messages) tuple
    }

    class MistralConfig {
        +str api_key
        +str model
        +int rpm_limit
        +acquire() float
    }

    class OpenRouterConfig {
        +list api_keys
        +str model
        +int rpm_limit
        +acquire_key() tuple
    }

    class DualConfig {
        +MistralConfig thinker
        +OpenRouterConfig actor
        +is_dual: bool
    }

    DualModelOrchestrator --> MistralThinker : 計画・評価
    DualModelOrchestrator --> InteractiveOrchestrator : 実行委譲
    DualModelOrchestrator --> WorkflowGraph : 制御フロー
    InteractiveOrchestrator --> OpenRouterAgent : ReAct 実行
    AgentOrchestrator --> OpenRouterAgent : Plan 実行
    AgentOrchestrator --> WorkflowGraph : 制御フロー
    MistralThinker --> MistralConfig : API設定
    OpenRouterAgent --> OpenRouterConfig : API設定
    OpenRouterAgent --> ToolRegistry : ツール実行
    DualConfig --> MistralConfig : Thinker設定
    DualConfig --> OpenRouterConfig : Actor設定
    WorkflowGraph --> PlanStep : ステップ管理
```

## 10. ファイル構成と役割

```
mimic3/
├── __main__.py          # エントリポイント: 設定ロード・初期化・メインループ
├── main.py              # interactive_loop() / pipe_mode() / auto_mode()
├── config.py            # .env パーサー / DualConfig / OpenRouterConfig / MistralConfig
├── orchestrator.py      # DualModelOrchestrator / AgentOrchestrator / InteractiveOrchestrator / WorkflowGraph
├── thinker.py           # MistralThinker (Mistral Large 3 専用 Thinker)
├── agent.py             # OpenRouterAgent (ReAct ループ + ツール実行)
├── tools.py             # ToolRegistry (ツール定義・実行)
├── commands.py          # スラッシュコマンド (/mode, /think, /model, /cd, ...)
├── autogit.py           # AutoGit (自動バックアップ・チェックポイント)
├── mcp_server.py        # MCP Server (Claude Code 連携)
├── utils.py             # ユーティリティ (TokenBucket, safe_print, log, ...)
└── .env                 # API キー・モデル設定
```

## 11. Dual モード タイムライン図

```
ユーザー入力
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 1: 計画生成 (Thinker)                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │ plan()   │───▶│ JSON生成 │───▶│ ユーザー │          │
│  │ (Mistral)│    │ (ストリーム)│   │ 承認[y/N]│          │
│  └──────────┘    └──────────┘    └──────────┘          │
└─────────────────────────────────────────────────────────┘
    │ 承認
    ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 2: 適応型ワークフロー (AdaptiveWorkflow)          │
│                                                         │
│  ┌─────────┐   ┌─────────┐   ┌──────────────┐         │
│  │ Actor   │──▶│ Thinker │──▶│ action判定   │         │
│  │ 実行    │   │ step_   │   │ continue/    │         │
│  │(ReAct)  │   │ review()│   │ replan/done  │         │
│  └─────────┘   └─────────┘   └──────────────┘         │
│       ▲                            │                    │
│       │         replan時           │                    │
│       └────────────────────────────┘                    │
│  (WorkflowGraph: on_failure/on_success/goto 処理)       │
└─────────────────────────────────────────────────────────┘
    │ 全ステップ完了
    ▼
┌─────────────────────────────────────────────────────────┐
│  Phase 3: 最終レビュー (Thinker)                         │
│  ┌──────────┐    ┌──────────┐                          │
│  │ review() │───▶│ 完了報告 │──▶ ユーザーへ返却        │
│  │ (Mistral)│    │ 課題・推奨│                          │
│  └──────────┘    └──────────┘                          │
└─────────────────────────────────────────────────────────┘
```
