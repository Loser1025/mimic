import json, urllib.request, urllib.parse, sys, time
import jwt # Now installed
from cryptography.hazmat.primitives import serialization

sys.stdout.reconfigure(encoding='utf-8')

# ── 設定 ──────────────────────────────────
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'
SSID = '1EmVvi7TwjrTc5Mx9wZjqo8G0ZCDrULUqPiD9oeDd97Y'
SHEET_NAME = '約束集計表'

# 範囲設定 A2:O6
# Row 2 -> index 1
# Row 6 -> index 5 (inclusive), so endRowIndex = 6
# Col A -> index 0
# Col O -> index 14 (inclusive), so endColumnIndex = 15
START_ROW = 1
END_ROW = 6
START_COL = 0
END_COL = 15

# ===== カラーパレット =====
NAVY_DARK    = {"red": 0.17, "green": 0.24, "blue": 0.31}  # #2B3E4F
NAVY_LIGHT   = {"red": 0.94, "green": 0.96, "blue": 0.98}  # #F0F5FA
WHITE        = {"red": 1.0,   "green": 1.0,   "blue": 1.0  }
DARK_TEXT    = {"red": 0.1,   "green": 0.1,   "blue": 0.2  }
BORDER_COLOR = {"red": 0.7,   "green": 0.7,   "blue": 0.7  }

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

# 秘密鍵の読み込みと署名
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
            "top": {"style": "SOLID_MEDIUM", "color": NAVY_DARK},
            "bottom": {"style": "SOLID_MEDIUM", "color": NAVY_DARK},
            "left": {"style": "SOLID_MEDIUM", "color": NAVY_DARK},
            "right": {"style": "SOLID_MEDIUM", "color": NAVY_DARK},
            "innerHorizontal": {"style": "SOLID", "color": BORDER_COLOR},
            "innerVertical": {"style": "SOLID", "color": BORDER_COLOR}
        }
    }

requests = []

# 1. ヘッダー (A2:O2) -> index 1 to 2
requests.append(repeat_cell(1, 2, 0, 15, 
    cell_format(NAVY_DARK, WHITE, bold=True, font_size=11)))

# 2. データ行 (A3:O6) -> index 2 to 6
for row in range(2, 6):
    bg = WHITE if row % 2 == 0 else NAVY_LIGHT
    requests.append(repeat_cell(row, row + 1, 0, 15, 
        cell_format(bg, DARK_TEXT, font_size=10)))

# 3. 枠線の適用 (A2:O6)
requests.append(update_borders(1, 6, 0, 15))

# 実行
body = json.dumps({"requests": requests}).encode()
response = urllib.request.urlopen(urllib.request.Request(
    f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}:batchUpdate',
    data=body,
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
)).read()

result = json.loads(response)
print(f"完了: {len(result.get('replies', []))} 件のリクエスト処理済み")
print("✓ 約束集計表 A2:O6 のデザイン適用完了")
