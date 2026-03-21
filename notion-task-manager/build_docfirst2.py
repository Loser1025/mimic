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
TARGET_PAGE_ID = "327f0edf-6de5-8063-9f5d-e25b3946947f"  # ドキュメントファースト

def req(method, path, data=None):
    url = f"https://api.notion.com/v1/{path}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    r = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        print(f"ERROR {e.code}: {json.loads(e.read())}")
        return None

def t(content, bold=False, color="default"):
    return {
        "type": "text",
        "text": {"content": content, "link": None},
        "annotations": {"bold": bold, "italic": False, "strikethrough": False,
                        "underline": False, "code": False, "color": color}
    }

# ============================================================
# 1. 提案ドキュメントDBを作成
# ============================================================
print("1. 提案DBを作成中...")
db = req("POST", "databases", {
    "parent": {"type": "page_id", "page_id": TARGET_PAGE_ID},
    "title": [{"text": {"content": "提案ドキュメント一覧"}}],
    "properties": {
        "タイトル": {"title": {}},
        "ステータス": {
            "select": {"options": [
                {"name": "起草中",     "color": "gray"},
                {"name": "レビュー中", "color": "yellow"},
                {"name": "議論済み",   "color": "blue"},
                {"name": "採用",       "color": "green"},
                {"name": "見送り",     "color": "red"},
            ]}
        },
        "カテゴリ": {
            "select": {"options": [
                {"name": "脚本",             "color": "purple"},
                {"name": "トークスクリプト", "color": "pink"},
                {"name": "スライド",         "color": "orange"},
                {"name": "セッション動画",   "color": "blue"},
                {"name": "その他",           "color": "gray"},
            ]}
        },
        "提案者":       {"rich_text": {}},
        "コメント期限": {"date": {}},
        "優先度": {
            "select": {"options": [
                {"name": "高", "color": "red"},
                {"name": "中", "color": "yellow"},
                {"name": "低", "color": "gray"},
            ]}
        },
    }
})
db_id = db["id"]
print(f"   完了: {db_id}")

# ============================================================
# 2. サンプル提案を追加
# ============================================================
print("2. サンプル提案を追加中...")
sample_page = req("POST", "pages", {
    "parent": {"database_id": db_id},
    "properties": {
        "タイトル":     {"title": [{"text": {"content": "【サンプル】トークスクリプト改善提案"}}]},
        "ステータス":   {"select": {"name": "レビュー中"}},
        "カテゴリ":     {"select": {"name": "トークスクリプト"}},
        "提案者":       {"rich_text": [{"text": {"content": "ひろたさん"}}]},
        "コメント期限": {"date": {"start": "2026-03-19"}},
        "優先度":       {"select": {"name": "高"}},
    }
})
sample_id = sample_page["id"]

req("PATCH", f"blocks/{sample_id}/children", {"children": [
    {"object": "block", "type": "callout", "callout": {
        "rich_text": [t("このページはサンプルです。新しい提案を作るときはこのフォーマットをコピーして使ってください。")],
        "icon": {"type": "emoji", "emoji": "📋"},
        "color": "yellow_background"
    }},
    {"object": "block", "type": "divider", "divider": {}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("背景・問題意識")]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        t("（例）週1回の定例会議だけでは時間が足りず、詳細な擦り合わせができていない。\nその結果、想定と違う着地になることがある。")
    ]}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("目的")]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        t("（例）定例前に非同期で意見を集め、議論の質と効率を上げる。")
    ]}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("具体案")]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [
        t("提案者がドキュメントに「背景・目的・具体案・懸念点」をまとめる")
    ]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [
        t("メンバーは24時間以内にコメント機能で意見を書き込む")
    ]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [
        t("定例会議では既に合意している前提で、判断・決定に集中する")
    ]}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("懸念点・リスク")]}},
    {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        t("（例）ドキュメントを書く負荷が増える。\n→ 箇条書きでも可・完璧でなくてよいとルール化することで解消できる。")
    ]}},
    {"object": "block", "type": "divider", "divider": {}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("コメント欄（メンバーはここに記入）")], "color": "blue"}},
    {"object": "block", "type": "callout", "callout": {
        "rich_text": [t("コメント期限までにご意見をお願いします。賛成・反対・修正案など何でもOKです。")],
        "icon": {"type": "emoji", "emoji": "✏️"},
        "color": "blue_background"
    }},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [t("（名前）：意見をここに書く")]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [t("（名前）：意見をここに書く")]}},
]})
print(f"   完了: {sample_id}")

# ============================================================
# 3. メインページにガイドを追加
# ============================================================
print("3. ガイドページを構築中...")
req("PATCH", f"blocks/{TARGET_PAGE_ID}/children", {"children": [
    {"object": "block", "type": "callout", "callout": {
        "rich_text": [t("週1回の定例だけでは時間が足りない。このページは「非同期×テキストベース」で改善スピードを上げるための仕組みです。")],
        "icon": {"type": "emoji", "emoji": "💡"},
        "color": "yellow_background"
    }},
    {"object": "block", "type": "divider", "divider": {}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("この仕組みの3つのメリット")]}},
    {"object": "block", "type": "column_list", "column_list": {"children": [
        {"object": "block", "type": "column", "column": {"children": [
            {"object": "block", "type": "callout", "callout": {
                "rich_text": [t("アジャイル化\n", bold=True), t("定例前に細かく擦り合わせを繰り返す")],
                "icon": {"type": "emoji", "emoji": "⚡"},
                "color": "gray_background"
            }}
        ]}},
        {"object": "block", "type": "column", "column": {"children": [
            {"object": "block", "type": "callout", "callout": {
                "rich_text": [t("高品質化\n", bold=True), t("自分のペースで深く考え、言語化された意見を得る")],
                "icon": {"type": "emoji", "emoji": "🎯"},
                "color": "gray_background"
            }}
        ]}},
        {"object": "block", "type": "column", "column": {"children": [
            {"object": "block", "type": "callout", "callout": {
                "rich_text": [t("ナレッジ化\n", bold=True), t("ドキュメントがそのまま議事録・ナレッジになる")],
                "icon": {"type": "emoji", "emoji": "📚"},
                "color": "gray_background"
            }}
        ]}},
    ]}},
    {"object": "block", "type": "divider", "divider": {}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("運用フロー")]}},
    {"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": [
        t("提案者がドキュメントを作成", bold=True), t("（下のDBで新規ページを追加）")
    ]}},
    {"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": [
        t("背景・目的・具体案・懸念点を記入")
    ]}},
    {"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": [
        t("ステータスを「レビュー中」に変更", bold=True), t("→ メンバーに共有")
    ]}},
    {"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": [
        t("メンバーは24時間以内にコメント欄へ意見を記入")
    ]}},
    {"object": "block", "type": "numbered_list_item", "numbered_list_item": {"rich_text": [
        t("定例会議で最終判断", bold=True), t("→「採用」または「見送り」にステータス更新")
    ]}},
    {"object": "block", "type": "divider", "divider": {}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("活用シーン")]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [t("脚本作成")]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [t("トークスクリプト改善")]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [t("スライド前の要件定義")]}},
    {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [t("セッション動画へのフィードバック")]}},
    {"object": "block", "type": "divider", "divider": {}},
    {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [t("提案ドキュメント一覧")]}},
    {"object": "block", "type": "callout", "callout": {
        "rich_text": [t("新しい提案は「+新規」から追加。サンプルページのフォーマットをコピーして使ってください。")],
        "icon": {"type": "emoji", "emoji": "👇"},
        "color": "blue_background"
    }},
]})

print(f"\n完成!")
print(f"URL: https://www.notion.so/{TARGET_PAGE_ID.replace('-', '')}")
