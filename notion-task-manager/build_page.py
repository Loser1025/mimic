import urllib.request
import urllib.error
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

TOKEN = os.environ.get("NOTION_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}
PAGE_ID  = "327f0edf-6de5-812a-9620-e730f864397b"   # タスク管理ツール（ClaudeCode版）
COPY_DB_ID = "327f0edf-6de5-81ae-89d2-d9ff1a7de6d5"

def req(method, path, data=None):
    url = f"https://api.notion.com/v1/{path}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    r = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"ERROR {e.code}: {err}")
        return None

def text(content, bold=False, color="default"):
    ann = {"bold": bold, "italic": False, "strikethrough": False,
           "underline": False, "code": False, "color": color}
    return {"type": "text", "text": {"content": content, "link": None}, "annotations": ann}

# ---- ステータス集計 ----
db_data = req("POST", f"databases/{COPY_DB_ID}/query", {})
tasks = db_data["results"]
counts = {"未着手": 0, "進行中": 0, "完了": 0}
for t in tasks:
    s = t["properties"].get("ステータス", {}).get("select")
    if s:
        counts[s["name"]] = counts.get(s["name"], 0) + 1

total = len(tasks)

# ---- ページにブロックを追加 ----
blocks = [
    # ヘッダー説明
    {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [text(f"このページはClaudeCodeが自動生成したタスク管理ツールです。元データ（タスク表）はそのまま保護されています。")],
            "icon": {"type": "emoji", "emoji": "🤖"},
            "color": "blue_background"
        }
    },
    # 区切り
    {"object": "block", "type": "divider", "divider": {}},
    # 進捗サマリー見出し
    {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [text("進捗サマリー")], "color": "default"}
    },
    # 3カラム風にcolumn_listで並べる
    {
        "object": "block", "type": "column_list",
        "column_list": {
            "children": [
                {
                    "object": "block", "type": "column",
                    "column": {"children": [
                        {
                            "object": "block", "type": "callout",
                            "callout": {
                                "rich_text": [
                                    text("未着手\n", bold=True),
                                    text(f"{counts['未着手']} / {total} 件", bold=False, color="gray")
                                ],
                                "icon": {"type": "emoji", "emoji": "⬜"},
                                "color": "gray_background"
                            }
                        }
                    ]}
                },
                {
                    "object": "block", "type": "column",
                    "column": {"children": [
                        {
                            "object": "block", "type": "callout",
                            "callout": {
                                "rich_text": [
                                    text("進行中\n", bold=True),
                                    text(f"{counts['進行中']} / {total} 件", bold=False, color="blue")
                                ],
                                "icon": {"type": "emoji", "emoji": "🔵"},
                                "color": "blue_background"
                            }
                        }
                    ]}
                },
                {
                    "object": "block", "type": "column",
                    "column": {"children": [
                        {
                            "object": "block", "type": "callout",
                            "callout": {
                                "rich_text": [
                                    text("完了\n", bold=True),
                                    text(f"{counts['完了']} / {total} 件", bold=False, color="green")
                                ],
                                "icon": {"type": "emoji", "emoji": "✅"},
                                "color": "green_background"
                            }
                        }
                    ]}
                },
            ]
        }
    },
    {"object": "block", "type": "divider", "divider": {}},
    # 進行中タスク一覧
    {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [text("進行中タスク")], "color": "blue"}
    },
]

# 進行中タスクをcalloutで列挙
for t in tasks:
    props = t["properties"]
    s = props.get("ステータス", {}).get("select")
    if not s or s["name"] != "進行中":
        continue
    name_parts = props.get("名前", {}).get("title", [])
    name = "".join([x["plain_text"] for x in name_parts])
    na_parts = props.get("NA", {}).get("rich_text", [])
    na = "".join([x["plain_text"] for x in na_parts])
    goal_parts = props.get("GOAL", {}).get("rich_text", [])
    goal = "".join([x["plain_text"] for x in goal_parts])
    date = props.get("期限", {}).get("date")
    due_str = f"  期限: {date['start']}" if date else ""

    content = f"{name}{due_str}"
    detail = ""
    if goal:
        detail += f"GOAL: {goal}\n"
    if na:
        detail += f"NA: {na}"

    blocks.append({
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [text(content, bold=True)] + ([text(f"\n{detail.rstrip()}")] if detail else []),
            "icon": {"type": "emoji", "emoji": "🔵"},
            "color": "blue_background"
        }
    })

# 未着手タスク一覧
blocks += [
    {"object": "block", "type": "divider", "divider": {}},
    {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [text("未着手タスク")], "color": "gray"}
    },
]
for t in tasks:
    props = t["properties"]
    s = props.get("ステータス", {}).get("select")
    if not s or s["name"] != "未着手":
        continue
    name_parts = props.get("名前", {}).get("title", [])
    name = "".join([x["plain_text"] for x in name_parts])
    na_parts = props.get("NA", {}).get("rich_text", [])
    na = "".join([x["plain_text"] for x in na_parts])
    goal_parts = props.get("GOAL", {}).get("rich_text", [])
    goal = "".join([x["plain_text"] for x in goal_parts])
    date = props.get("期限", {}).get("date")
    due_str = f"  期限: {date['start']}" if date else ""

    content = f"{name}{due_str}"
    detail = ""
    if goal:
        detail += f"GOAL: {goal}\n"
    if na:
        detail += f"NA: {na}"

    blocks.append({
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [text(content, bold=True)] + ([text(f"\n{detail.rstrip()}")] if detail else []),
            "icon": {"type": "emoji", "emoji": "⬜"},
            "color": "gray_background"
        }
    })

# 完了タスク見出し
blocks += [
    {"object": "block", "type": "divider", "divider": {}},
    {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [text("完了タスク")], "color": "green"}
    },
]
for t in tasks:
    props = t["properties"]
    s = props.get("ステータス", {}).get("select")
    if not s or s["name"] != "完了":
        continue
    name_parts = props.get("名前", {}).get("title", [])
    name = "".join([x["plain_text"] for x in name_parts])
    goal_parts = props.get("GOAL", {}).get("rich_text", [])
    goal = "".join([x["plain_text"] for x in goal_parts])
    na_parts = props.get("NA", {}).get("rich_text", [])
    na = "".join([x["plain_text"] for x in na_parts])

    detail = ""
    if goal:
        detail += f"GOAL: {goal}\n"
    if na:
        detail += f"NA: {na}"

    blocks.append({
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [text(name, bold=True)] + ([text(f"\n{detail.rstrip()}")] if detail else []),
            "icon": {"type": "emoji", "emoji": "✅"},
            "color": "green_background"
        }
    })

# 使い方ガイド
blocks += [
    {"object": "block", "type": "divider", "divider": {}},
    {
        "object": "block", "type": "heading_2",
        "heading_2": {"rich_text": [text("使い方")], "color": "default"}
    },
    {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [text("下のデータベースでタスクを追加・編集できます")]}
    },
    {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [text("ステータスを「未着手→進行中→完了」に変更するだけでOK")]}
    },
    {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [text("NAには「次にやること（具体的なアクション）」を書く")]}
    },
    {
        "object": "block", "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [text("GOALには「このタスクが完了した状態」を書く")]}
    },
    {
        "object": "block", "type": "callout",
        "callout": {
            "rich_text": [text("データベースのビューを「ボード」に切り替えると、カンバン形式で管理できます")],
            "icon": {"type": "emoji", "emoji": "💡"},
            "color": "yellow_background"
        }
    },
]

# ページにブロック追加
print("ページにブロックを追加中...")
result = req("PATCH", f"blocks/{PAGE_ID}/children", {"children": blocks})
if result:
    print("完了!")
    print(f"URL: https://www.notion.so/{PAGE_ID.replace('-', '')}")
else:
    print("失敗")
