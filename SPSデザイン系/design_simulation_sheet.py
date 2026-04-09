import json
import urllib.request
import urllib.parse

# --- 設定 ---
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'
# Google API Token (環境変数やファイルから取得することを想定していますが、ここでは直接指定します)
# 本来はセキュアな方法で管理してください
TOKEN = 'ya29.a0AfB... (省略) ...' # 実際のトークンは環境から読み込むか、事前に設定されている前提

# 実際にはユーザーの環境にある token.txt 等から読み込む実装に変更します
try:
    with open(r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\token.txt', 'r') as f:
        TOKEN = f.read().strip()
except FileNotFoundError:
    print("Error: token.txt not found.")
    exit(1)

def hex_to_rgb(hex_code):
    hex_code = hex_code.lstrip('#')
    return {
        'red': int(hex_code[0:2], 16) / 255.0,
        'green': int(hex_code[2:4], 16) / 255.0,
        'blue': int(hex_code[4:6], 16) / 255.0
    }

# 🎨 モダン・ダッシュボード配色 (Slate & Indigo)
COLOR_HEADER_BG = hex_to_rgb('#1E293B')    # Slate-800
COLOR_HEADER_TEXT = hex_to_rgb('#F8FAFC')  # Slate-50
COLOR_ALT_ROW_BG = hex_to_rgb('#F1F5F9')   # Slate-100
COLOR_BORDER = hex_to_rgb('#CBD5E1')       # Slate-300

def run_request(url, method='GET', body=None):
    req = urllib.request.Request(url, method=method, headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'})
    if body:
        req.data = json.dumps(body).encode('utf-8')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

# 1. シートIDの取得
spreadsheet = run_request(f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}')
sheet_id = next(s['properties']['sheetId'] for s in spreadsheet['sheets'] if s['properties']['title'] == SHEET_NAME)

# 2. データ範囲の取得 (シングルクォートで囲んでエンコード)
encoded_range = urllib.parse.quote(f"'{SHEET_NAME}'")
values_resp = run_request(f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}/values/{encoded_range}')
values = values_resp.get('values', [])

if not values:
    print("No data found in sheet.")
    exit(0)

rows = len(values)
cols = max(len(row) for row in values)

# 3. 書式設定リクエストの構築
requests = []

# A. 全体の基本フォントと配置
requests.append({
    "repeatCell": {
        "range": {"sheetId": sheet_id},
        "cell": {
            "userEnteredFormat": {
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
                "textFormat": {"fontSize": 10}
            }
        },
        "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat)"
    }
})

# B. ヘッダーのデザイン
requests.append({
    "repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
        "cell": {
            "userEnteredFormat": {
                "backgroundColor": COLOR_HEADER_BG,
                "textFormat": {
                    "foregroundColor": COLOR_HEADER_TEXT,
                    "bold": True,
                    "fontSize": 11
                },
                "horizontalAlignment": "CENTER"
            }
        },
        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
    }
})

# C. 交互行の色付け (ストライプ)
for r in range(1, rows):
    if r % 2 == 1:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": r, "endRowIndex": r + 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_ALT_ROW_BG
                    }
                },
                "fields": "userEnteredFormat(backgroundColor)"
            }
        })

# D. 外枠と内枠の罫線
requests.append({
    "updateCells": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": rows, "startColumnIndex": 0, "endColumnIndex": cols},
        "fields": "userEnteredFormat.borders"
    }
})
# 簡易的に全セルに薄いグレーの線を引く (APIの制限で一括指定が複雑なため、全域に適用)
requests.append({
    "repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": rows, "startColumnIndex": 0, "endColumnIndex": cols},
        "cell": {
            "userEnteredFormat": {
                "borders": {
                    "top": {"style": "SOLID", "color": COLOR_BORDER},
                    "bottom": {"style": "SOLID", "color": COLOR_BORDER},
                    "left": {"style": "SOLID", "color": COLOR_BORDER},
                    "right": {"style": "SOLID", "color": COLOR_BORDER},
                }
            }
        },
        "fields": "userEnteredFormat.borders"
    }
})

# E. 列幅の自動調整 (簡易的に各列を120pxに)
for c in range(cols):
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": 120},
            "fields": "pixelSize"
        }
    })

# F. ヘッダーの固定
requests.append({
    "updateSheetProperties": {
        "properties": {
            "sheetId": sheet_id,
            "gridProperties": {"frozenRowCount": 1}
        },
        "fields": "gridProperties.frozenRowCount"
    }
})

# 実行
payload = {"requests": requests}
run_request(f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}:batchUpdate', method='POST', body=payload)

print("✅ Design applied successfully!")
