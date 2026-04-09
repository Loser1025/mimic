import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==============================================================================
# 設定情報
# ==============================================================================
# 認証情報のパス
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'
# スプレッドシートID
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
# 対象シート名
SHEET_NAME = 'WEB/シミュ2'

# カラーパレット (Modern Slate-Indigo)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}  # Slate-800
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} # Slate-50
COLOR_ALT_ROW = {"red": 0.941, "green": 0.961, "blue": 0.976}    # Slate-100
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}     # Slate-300

def design_sheet():
    try:
        # 1. 認証
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, 
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)

        # 2. シートIDの取得
        spreadsheet = service.spreadsheets().get(spreadsheetId=SSID).execute()
        sheet_id = next(s['properties']['sheetId'] for s in spreadsheet['sheets'] if s['properties']['title'] == SHEET_NAME)
        
        # 3. データ範囲の特定 (A1形式で全データを取得してサイズを把握)
        result = service.spreadsheets().values().get(
            spreadsheetId=SSID, 
            range=f"'{SHEET_NAME}'"
        ).execute()
        values = result.get('values', [])
        if not values:
            print("❌ データが見つかりませんでした。")
            return
        
        row_count = len(values)
        col_count = len(values[0]) if row_count > 0 else 0

        # 4. デザインリクエストの構築
        requests = []

        # --- ヘッダーのデザイン (1行目) ---
        requests.append({
            "repeatCell": {
                "range": { "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": col_count },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_HEADER_BG,
                        "textFormat": { "foregroundColor": COLOR_HEADER_TEXT, "bold": True },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "borders": {
                            "top": {"style": "SOLID", "color": COLOR_BORDER},
                            "bottom": {"style": "SOLID", "color": COLOR_BORDER},
                            "left": {"style": "SOLID", "color": COLOR_BORDER},
                            "right": {"style": "SOLID", "color": COLOR_BORDER},
                        }
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,borders)"
            }
        })

        # --- データ行のデザイン (2行目以降) ---
        requests.append({
            "repeatCell": {
                "range": { "sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": row_count, "startColumnIndex": 0, "endColumnIndex": col_count },
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "LEFT",
                        "verticalAlignment": "MIDDLE",
                        "borders": {
                            "top": {"style": "SOLID", "color": COLOR_BORDER},
                            "bottom": {"style": "SOLID", "color": COLOR_BORDER},
                            "left": {"style": "SOLID", "color": COLOR_BORDER},
                            "right": {"style": "SOLID", "color": COLOR_BORDER},
                        }
                    }
                },
                "fields": "userEnteredFormat(horizontalAlignment,verticalAlignment,borders)"
            }
        })

        # --- ストライプ(交互色)の設定 ---
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{ "sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": row_count, "startColumnIndex": 0, "endColumnIndex": col_count }],
                    "booleanRule": {
                        "condition": { "type": "CUSTOM_FORMULA", "values": [{ "userEnteredValue": "=ISEVEN(ROW())" }] },
                        "format": { "backgroundColor": COLOR_ALT_ROW }
                    }
                },
                "index": 0
            }
        })

        # --- 1行目の固定 ---
        requests.append({
            "updateSheetProperties": {
                "properties": { "sheetId": sheet_id, "gridProperties": { "frozenRowCount": 1 } },
                "fields": "gridProperties.frozenRowCount"
            }
        })

        # --- 列幅の自動調整 (修正済み: autoResizeDimensions) ---
        requests.append({
            "autoResizeDimensions": {
                "dimensions": { "sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": col_count }
            }
        })

        # 5. 実行
        body = {'requests': requests}
        service.spreadsheets().batchUpdate(spreadsheetId=SSID, body=body).execute()
        print("✅ デザインの適用に成功しました！")

    except Exception as e:
        print(f"❌ エラー発生: {e}")

if __name__ == '__main__':
    design_sheet()
