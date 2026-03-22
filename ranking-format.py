import json, urllib.request, urllib.parse, sys
sys.stdout.reconfigure(encoding='utf-8')

creds = json.load(open('C:/Users/弁護士法人響/.config/gws/authorized_user.json'))
token = json.loads(urllib.request.urlopen(urllib.request.Request(
    'https://oauth2.googleapis.com/token',
    data=urllib.parse.urlencode({**creds, 'grant_type': 'refresh_token'}).encode()
)).read())['access_token']

ssid = '1d6_Q3ws9yIEbCUZAMfaWqb2rZ_fjrJdLqruMWucg3pU'
sheet_id = 1925468628

# ===== カラーパレット =====
HEADER_BG    = {"red": 0.063, "green": 0.082, "blue": 0.208}  # #101535 最濃紺
HEADER_TEXT  = {"red": 1.0,   "green": 1.0,   "blue": 1.0  }  # 白
GOLD_BG      = {"red": 1.0,   "green": 0.800, "blue": 0.0  }  # #FFCC00 金（濃いめ）
GOLD_TEXT    = {"red": 0.133, "green": 0.133, "blue": 0.133}  # 濃グレー
SILVER_BG    = {"red": 0.620, "green": 0.620, "blue": 0.620}  # #9E9E9E 銀（濃いめ）
SILVER_TEXT  = {"red": 1.0,   "green": 1.0,   "blue": 1.0  }  # 白
BRONZE_BG    = {"red": 0.627, "green": 0.322, "blue": 0.176}  # #A0522D 銅（濃いめ）
BRONZE_TEXT  = {"red": 1.0,   "green": 1.0,   "blue": 1.0  }  # 白
TOP_BG       = {"red": 0.086, "green": 0.396, "blue": 0.753}  # #1565C0 4-6位（濃青）
TOP_TEXT     = {"red": 1.0,   "green": 1.0,   "blue": 1.0  }  # 白
MID_BG       = {"red": 0.878, "green": 0.929, "blue": 0.996}  # #E0EDF9 中位（薄青）
BOTTOM_BG    = {"red": 0.898, "green": 0.224, "blue": 0.208}  # #E53935 下位6人（赤）
BOTTOM_TEXT  = {"red": 1.0,   "green": 1.0,   "blue": 1.0  }  # 白
DARK_TEXT    = {"red": 0.133, "green": 0.133, "blue": 0.133}

BORDER_OUTER = {"red": 0.063, "green": 0.082, "blue": 0.208}  # ヘッダーと同色
BORDER_INNER = {"red": 0.565, "green": 0.694, "blue": 0.820}  # #90B1D1


def border(color, style="SOLID"):
    return {"style": style, "color": color}

def cell_format(bg, text_color=None, bold=False, font_size=None, align="CENTER"):
    tf = {}
    if text_color:
        tf["foregroundColor"] = text_color
    if bold:
        tf["bold"] = True
    if font_size:
        tf["fontSize"] = font_size
    fmt = {"backgroundColor": bg, "horizontalAlignment": align}
    if tf:
        fmt["textFormat"] = tf
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
    outer = border(BORDER_OUTER, "SOLID_MEDIUM")
    inner = border(BORDER_INNER, "SOLID")
    return {
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": row_start,
                "endRowIndex": row_end,
                "startColumnIndex": col_start,
                "endColumnIndex": col_end
            },
            "top": outer, "bottom": outer, "left": outer, "right": outer,
            "innerHorizontal": inner, "innerVertical": inner
        }
    }

def format_table(header_row, data_start, data_end, col_count):
    """ランキング表一つ分のフォーマットリクエストを生成"""
    reqs = []
    cols = col_count

    # ヘッダー行
    reqs.append(repeat_cell(header_row, header_row + 1, 0, cols,
        cell_format(HEADER_BG, HEADER_TEXT, bold=True, font_size=11)))

    # 1位（金）
    reqs.append(repeat_cell(data_start, data_start + 1, 0, cols,
        cell_format(GOLD_BG, GOLD_TEXT, bold=True, font_size=10)))

    # 2位（銀）
    reqs.append(repeat_cell(data_start + 1, data_start + 2, 0, cols,
        cell_format(SILVER_BG, SILVER_TEXT, bold=True, font_size=10)))

    # 3位（銅）
    reqs.append(repeat_cell(data_start + 2, data_start + 3, 0, cols,
        cell_format(BRONZE_BG, BRONZE_TEXT, bold=True, font_size=10)))

    # 4-6位（濃青・上位ゾーン）
    top6_end = data_start + 6
    if data_start + 3 < top6_end:
        reqs.append(repeat_cell(data_start + 3, top6_end, 0, cols,
            cell_format(TOP_BG, TOP_TEXT, font_size=10)))

    # 中位（7位〜下位6人の手前）
    bottom6_start = max(top6_end, data_end - 6)
    if top6_end < bottom6_start:
        reqs.append(repeat_cell(top6_end, bottom6_start, 0, cols,
            cell_format(MID_BG, DARK_TEXT, font_size=10)))

    # 下位6人（赤・警戒ゾーン）
    if bottom6_start < data_end:
        reqs.append(repeat_cell(bottom6_start, data_end, 0, cols,
            cell_format(BOTTOM_BG, BOTTOM_TEXT, bold=True, font_size=10)))

    # 枠線（ヘッダー含む全体）
    reqs.append(update_borders(header_row, data_end, 0, cols))

    return reqs


requests = []

# ===== ベース背景色（全体に薄いスレートブルーを塗布） =====
# 表のフォーマットが後から上書きするため、ギャップ行・右側列に残る
BASE_BG = {"red": 0.910, "green": 0.929, "blue": 0.961}  # #E8EDF5 薄スレートブルー
requests.append({
    "repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 130,
                  "startColumnIndex": 0, "endColumnIndex": 15},
        "cell": {"userEnteredFormat": {"backgroundColor": BASE_BG}},
        "fields": "userEnteredFormat.backgroundColor"  # 背景色のみ変更・文字/値は保持
    }
})

# ===== タイトル（結合セル B1:I3 = row 0-2, col 1-8） =====
requests.append({
    "repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 3,
                  "startColumnIndex": 1, "endColumnIndex": 9},
        "cell": {
            "userEnteredFormat": {
                "backgroundColor": {"red": 0.063, "green": 0.082, "blue": 0.208},  # #101535
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": {
                    "foregroundColor": {"red": 1.0, "green": 0.800, "blue": 0.0},  # #FFCC00 ゴールド
                    "bold": True,
                    "fontSize": 20,
                    "fontFamily": "Arial"
                }
            }
        },
        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat)"
    }
})

# ===== タイトルテキストに絵文字を追加 =====
requests.append({
    "updateCells": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": 1, "endColumnIndex": 2},
        "rows": [{"values": [{"userEnteredValue": {"stringValue": "🏆 昇降格表3/16- 🏆"}}]}],
        "fields": "userEnteredValue"
    }
})

# ===== Table 1: あむA隊 =====
# ヘッダー: 行5 (0-indexed: 4), データ: 行6-35 (0-indexed: 5-34)
requests += format_table(header_row=4, data_start=5, data_end=35, col_count=9)

# ===== Table 2: あむB隊 =====
# ヘッダー: 行40 (0-indexed: 39), データ: 行41-59 (0-indexed: 40-59)
requests += format_table(header_row=39, data_start=40, data_end=59, col_count=9)

# ===== Table 3: あむC隊 =====
# ヘッダー: 行76 (0-indexed: 75), データ: 行77-120 (0-indexed: 76-120)
requests += format_table(header_row=75, data_start=76, data_end=120, col_count=8)

print(f"リクエスト数: {len(requests)}")

body = json.dumps({"requests": requests}).encode()
response = urllib.request.urlopen(urllib.request.Request(
    f'https://sheets.googleapis.com/v4/spreadsheets/{ssid}:batchUpdate',
    data=body,
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
)).read()

result = json.loads(response)
print(f"完了: {len(result.get('replies', []))} 件のリクエスト処理済み")
print("✓ ランキング表デザイン適用完了")
