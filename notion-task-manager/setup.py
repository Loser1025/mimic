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
SRC_DB_ID = "327f0edf-6de5-8010-b4ee-c2f561b0a211"
COPY_DB_ID = "327f0edf-6de5-81ae-89d2-d9ff1a7de6d5"  # 作成済みのコピーDB

def notion_request(method, path, data=None):
    url = f"https://api.notion.com/v1/{path}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"ERROR {e.code}: {err}")
        return None

# 元DBから全データ取得
print("元データ取得中...")
src_data = notion_request("POST", f"databases/{SRC_DB_ID}/query", {})
tasks = src_data["results"]
print(f"{len(tasks)}件取得")

# コピーDBに全データを追加
print("データをコピー中...")
for t in tasks:
    props = t["properties"]

    def get_text(prop_name):
        p = props.get(prop_name, {})
        texts = p.get("rich_text", [])
        return "".join([x["plain_text"] for x in texts]) if texts else ""

    def get_title(prop_name):
        p = props.get(prop_name, {})
        texts = p.get("title", [])
        return "".join([x["plain_text"] for x in texts]) if texts else ""

    def get_status(prop_name):
        p = props.get(prop_name, {})
        s = p.get("status") or p.get("select")
        return s["name"] if s else "未着手"

    def get_date(prop_name):
        p = props.get(prop_name, {})
        d = p.get("date")
        return d["start"] if d else None

    name = get_title("名前")
    status = get_status("ステータス")
    goal = get_text("GOAL")
    na = get_text("NA")
    memo = get_text("メモ")
    due = get_date("期限")

    new_props = {
        "名前": {"title": [{"text": {"content": name}}]},
        "ステータス": {"select": {"name": status}},
    }
    if goal:
        new_props["GOAL"] = {"rich_text": [{"text": {"content": goal}}]}
    if na:
        new_props["NA"] = {"rich_text": [{"text": {"content": na}}]}
    if memo:
        new_props["メモ"] = {"rich_text": [{"text": {"content": memo}}]}
    if due:
        new_props["期限"] = {"date": {"start": due}}

    result = notion_request("POST", "pages", {
        "parent": {"database_id": COPY_DB_ID},
        "properties": new_props
    })
    if result:
        print(f"OK: {name} [{status}]")
    else:
        print(f"NG: {name}")

print(f"\nDB ID: {COPY_DB_ID}")
