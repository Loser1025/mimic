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
SRC_DB_ID  = "327f0edf-6de5-8010-b4ee-c2f561b0a211"
COPY_DB_ID = "327f0edf-6de5-81ae-89d2-d9ff1a7de6d5"

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

# 1. コピーDBに「リスト」プロパティを追加
print("1. リストプロパティを追加中...")
result = req("PATCH", f"databases/{COPY_DB_ID}", {
    "properties": {
        "リスト": {
            "multi_select": {
                "options": [
                    {"name": "期限付き", "color": "yellow"},
                    {"name": "そのうちやること", "color": "orange"}
                ]
            }
        }
    }
})
print("   完了" if result else "   失敗")

# 2. 元DBから全タスク取得（名前とリスト値）
print("2. 元データのリスト値を取得中...")
src_data = req("POST", f"databases/{SRC_DB_ID}/query", {})
src_map = {}  # 名前 → リスト値
for t in src_data["results"]:
    props = t["properties"]
    name = "".join([x["plain_text"] for x in props.get("名前", {}).get("title", [])])
    list_vals = [opt["name"] for opt in props.get("リスト", {}).get("multi_select", [])]
    src_map[name] = list_vals
print(f"   {len(src_map)}件取得")

# 3. コピーDBの全タスクに対してリスト値を書き込む
print("3. コピーDBのタスクにリスト値を設定中...")
copy_data = req("POST", f"databases/{COPY_DB_ID}/query", {})
for t in copy_data["results"]:
    props = t["properties"]
    name = "".join([x["plain_text"] for x in props.get("名前", {}).get("title", [])])
    list_vals = src_map.get(name, [])
    if not list_vals:
        print(f"   スキップ: {name} (リストなし)")
        continue
    result = req("PATCH", f"pages/{t['id']}", {
        "properties": {
            "リスト": {
                "multi_select": [{"name": v} for v in list_vals]
            }
        }
    })
    print(f"   {'OK' if result else 'NG'}: {name} → {list_vals}")

print("完了!")
