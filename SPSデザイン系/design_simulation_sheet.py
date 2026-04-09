import json
import os
import urllib.request
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# 設定
# ==========================================
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'

# モダンUIカラーパレット (Slate-Indigo)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}    # #1E293B (Slate-800)
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98}   # #F8FAFC (Slate-50)
COLOR_ALT_ROW = {"red": 0.941, "green": 0.961, "blue": 0.976}       # #F1F5F9 (Slate-100)
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}       # #CBD5E1 (Slate-300)

def main():
    print(f"🚀 デザイン適用を開始します: {SHEET_NAME}")
    
    try:
        # 1. 認証
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, 
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)

        # 2. シートIDの取得
        spreadsheet = service.spreadsheets().get(spreadsheetId=SSID).execute()
        sheets = spreadsheet.get('sheets', [])
        sheet_id = None
        for s in sheets:
            if s['properties']['title'] == SHEET_NAME:
                sheet_id = s['properties']['sheetId']
                break
        
        if sheet_id is None:
            print(f"❌ エラー: シート '{SHEET_NAME}' が見つかりませんでした。")
            return

        # 3. データの範囲を確認
        result = service.spreadsheets().values().get(
            spreadsheetId=SSID, 
            range=f"'{SHEET_NAME}'"
        ).execute()
        values = result.get('values', [])
        if not values:
            print("⚠️ データが空のため、デザイン適用をスキップします。")
            return
        
        row_count = len(values)
        col_count = len(values[0]) if row_count > 0 else 0

        # 4. デザインリクエストの構築
        requests = []

        # --- ヘッダーデザイン ---
        requests.append({
            "repeatCell": {
                "range": { "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": col_count },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_HEADER_BG,
                        "textFormat": { "foregroundColor": COLOR_HEADER_TEXT, "bold": True },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # --- 全体の枠線 (Borders) ---
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

        # --- 交互行の色 (Alternating Colors) ---
        # 注意: addConditionalFormatRule よりも setBasicFilter 等の機能があるが、
        # シンプルに repeatCell で偶数行を塗るか、APIの 'addConditionalFormatRule' を使う。
        # ここでは最も確実な 'addConditionalFormatRule' を使用して「偶数行」を塗りつぶす。
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

        # --- 行の固定 (Freeze) ---
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": { "frozenRowCount": 1 }
                },
                "fields": "gridProperties.frozenRowCount"
            }
        })

        # --- 列幅の自動調整 (修正済みのフィールド名) ---
        requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": col_count
                }
            }
        })

        # 5. 一括適用
        body = { "requests": requests }
        service.spreadsheets().batchUpdate(spreadsheetId=SSID, body=body).execute()
        
        print("✅ デザインが正常に適用されました！")

    except Exception as e:
        print(f"❌ エラー発生: {e}")

if __name__ == '__main__':
    main()
