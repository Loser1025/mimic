import json, urllib.request, urllib.parse, sys, time
import jwt
from cryptography.hazmat.primitives import serialization

sys.stdout.reconfigure(encoding='utf-8')

# ── 設定 ──────────────────────────────────
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'

# ===== カラーパレット (Modern SaaS Dashboard Style) =====
# Slate 800 (#1E293B)
PRIMARY_DARK = {"red": 0.118, "green": 0.165, "blue": 0.231} 
# Slate 50 (#F8FAFC)
HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} 
# White (#FFFFFF)
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
# Slate 100 (#F1F5F9)
SECONDARY_LIGHT = {"red": 0.941, "green": 0.961, "blue": 0.976} 
# Slate 900 (#0F172A)
TEXT_DARK = {"red": 0.059, "green": 0.094, "blue": 0.165}
# Slate 300 (#CBD5E1)
BORDER_LIGHT = {"red": 0.796, "green": 0.835, "blue": 0.882}
# Slate 800 (#1E293B)
BORDER_PRIMARY = {"red": 0.118, "green": 0.165, "blue": 0.231}

# ── 認証トークン取得 ──────────────────────────
with open(SERVICE_ACCOUNT_FILE) as f:
    creds = json.load(f)

now = int(time.time())
payload = {
    'iss': creds['client_email'],
    'scope': 'https://www.googleapis.com/auth/spreadsheets',
    'aud': 'https://oauth2.googleapis.com/token',
    'exp': now + 3600,
    'iat': now
}

private_key = creds['private_key']
token_jwt = jwt.encode(payload, private_key, algorithm='RS256')

token_resp = urllib.request.urlopen(urllib.request.Request(
    'https://oauth2.googleapis.com/token',
    data=urllib.parse.urlencode({'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer', 'assertion': token_jwt}).encode()
)).read()
token = json.loads(token_resp)['access_token']

# ── シートIDの取得 ────────────────────────────
resp = urllib.request.urlopen(urllib.request.Request(
    f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}',
    headers={'Authorization': f'Bearer {token}'}
)).read()
spreadsheet = json.loads(resp)
sheet_id = next(s['properties']['sheetId'] for s in spreadsheet['sheets'] if s['properties']['title'] == SHEET_NAME)

# ── データ範囲の自動取得 ──────────────────────────
# 【修正】SHEET_NAME を URLエンコードする
encoded_sheet_name = urllib.parse.quote(SHEET_NAME)
val_resp = urllib.request.urlopen(urllib.request.Request(
    f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}/values/{encoded_sheet_name}',
    headers={'Authorization': f'Bearer {token}'}
)).read()
values = json.loads(val_resp).get('values', [])

if not values:
    print("データが見つかりませんでした。")
    sys.exit()

num_rows = len(values)
num_cols = max(len(row) for row in values)
print(f"データ範囲を検知: {num_rows}行 x {num_cols}列")

# ── フォーマット関数 ──────────────────────────
def cell_format(bg, text_color=None, bold=False, font_size=None, align="CENTER"):
    tf = {}
    if text_color: tf["foregroundColor"] = text_color
    if bold: tf["bold"] = True
    if font_size: tf["fontSize"] = font_size
    fmt = {"backgroundColor": bg, "horizontalAlignment": align}
    if tf: fmt["textFormat"] = tf
    return fmt

def repeat_cell(row_start, row_end, col_start, col_end, fmt):
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_start,
                "endRowIndex": row_end,
                "startColumnIndex": col_start,
                "endColumnIndex": col_end
            },
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }
    }

def update_borders(row_start, row_end, col_start, col_end):
    return {
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_start,
                "endRowIndex": row_end,
                "startColumnIndex": col_start,
                "endColumnIndex": col_end
            },
            "top": {"style": "SOLID_MEDIUM", "color": BORDER_PRIMARY},
            "bottom": {"style": "SOLID_MEDIUM", "color": BORDER_PRIMARY},
            "left": {"style": "SOLID_MEDIUM", "color": BORDER_PRIMARY},
            "right": {"style": "SOLID_MEDIUM", "color": BORDER_PRIMARY},
            "innerHorizontal": {"style": "SOLID", "color": BORDER_LIGHT},
            "innerVertical": {"style": "SOLID", "color": BORDER_LIGHT}
        }
    }

requests = []

# 1. ヘッダーデザイン (1行目: index 0 to 1)
requests.append(repeat_cell(0, 1, 0, num_cols, 
    cell_format(PRIMARY_DARK, HEADER_TEXT, bold=True, font_size=11)))

# 2. データ行のデザイン (2行目以降: index 1 to num_rows)
for row in range(1, num_rows):
    bg = WHITE if row % 2 != 0 else SECONDARY_LIGHT
    requests.append(repeat_cell(row, row + 1, 0, num_cols, 
        cell_format(bg, TEXT_DARK, font_size=10)))

# 3. 枠線の適用 (全体)
requests.append(update_borders(0, num_rows, 0, num_cols))

# 4. 1行目を固定 (Freeze)
requests.append({
    "updateSheetProperties": {
        "properties": {
            "sheetId": sheet_id,
            "gridProperties": {"frozenRowCount": 1}
        },
        "fields": "gridProperties.frozenRowCount"
    }
})

# 5. 列幅の自動調整
requests.append({
    "autoResizeDimensions": {
        "dimensions": {
            "sheetId": sheet_id,
            "dimension": "COLUMNS",
            "startIndex": 0,
            "endIndex": num_cols
        }
    }
})

# 実行
body = json.dumps({"requests": requests}).encode()
response = urllib.request.urlopen(urllib.request.Request(
    f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}:batchUpdate',
    data=body,
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
)).read()

result = json.loads(response)
print(f"完了: {len(result.get('replies', []))} 件のリクエスト処理済み")
print(f"✓ {SHEET_NAME} のデザイン適用完了 (Modern SaaS Style)")
