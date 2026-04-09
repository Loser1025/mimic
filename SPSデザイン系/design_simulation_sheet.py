import json
import urllib.request
import urllib.parse

# ==========================================
# 設定情報
# ==========================================
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'
TOKEN = 'ya29.a0AfB...) ' # ユーザー環境の有効なトークンが設定されている前提

# モダン・カラーパレット (Slate-Indigo)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}    # #1E293B (Slate-800)
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} # #F8FAFC (Slate-50)
COLOR_ALT_ROW_BG = {"red": 0.941, "green": 0.961, "blue": 0.976}  # #F1F5F9 (Slate-100)
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}      # #CBD5E1 (Slate-300)

def send_request(url, method='GET', data=None):
    req = urllib.request.Request(url, method=method, headers={'Authorization': f'Bearer {TOKEN}'})
    if data:
        req.add_data(json.dumps(data).encode('utf-8'))
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def main():
    print(f"🚀 デザイン適用を開始します: {SHEET_NAME}")

    # 1. シートIDの取得
    spreadsheet = send_request(f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}')
    sheet_id = next(s['properties']['sheetId'] for s in spreadsheet['sheets'] if s['properties']['title'] == SHEET_NAME)
    
    # 2. データ範囲（行数・列数）の取得
    # シート名に / が含まれるためシングルクォートで囲んでエンコード
    encoded_range = urllib.parse.quote(f"'{SHEET_NAME}'")
    val_data = send_request(f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}/values/{encoded_range}')
    
    values = val_data.get('values', [])
    if not values:
        print("❌ データが見つかりませんでした。")
        return
    
    row_count = len(values)
    col_count = len(values[0])
    print(f"📊 テーブルサイズ: {row_count}行 x {col_count}列")

    # 3. batchUpdate リクエストの構築
    requests = []

    # --- 全体に枠線を適用 (repeatCell) ---
    requests.append({
        "repeatCell": {
            "range": { "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": row_count, "startColumnIndex": 0, "endColumnIndex": col_count },
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

    # --- ヘッダー行のデザイン (BG, Text Color, Bold, Center) ---
    requests.append({
        "repeatCell": {
            "range": { "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": col_count },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER_BG,
                    "textFormat": { "foregroundColor": COLOR_HEADER_TEXT, "bold": True },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
        }
    })

    # --- 交互行の背景色適用 (SaaS風ストライプ) ---
    # 2行目から最後までのうち、偶数行に色をつける
    for r in range(1, row_count, 2):
        requests.append({
            "repeatCell": {
                "range": { "sheetId": sheet_id, "startRowIndex": r, "endRowIndex": r+1, "startColumnIndex": 0, "endColumnIndex": col_count },
                "cell": {
                    "userEnteredFormat": { "backgroundColor": COLOR_ALT_ROW_BG }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    # --- 行固定 (1行目) ---
    requests.append({
        "updateSheetProperties": {
            "properties": { "sheetId": sheet_id, "gridProperties": { "frozenRowCount": 1 } },
            "fields": "gridProperties.frozenRowCount"
        }
    })

    # --- 列幅の自動調整 ---
    requests.append({
        "autoResizeColumns": {
            "range": { "sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": col_count }
        }
    })

    # 4. 実行
    send_request(f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}:batchUpdate', method='POST', data={'requests': requests})
    print("✅ デザインの適用が完了しました！")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"❌ エラー発生: {e}")
