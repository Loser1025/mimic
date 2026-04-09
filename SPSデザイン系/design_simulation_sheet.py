import os
import json
import urllib.parse
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ================= 設定 =================
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'

# モダン配色 (Slate-Indigo)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}  # #1E293B
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} # #F8FAFC
COLOR_ALT_ROW = {"red": 0.941, "green": 0.961, "blue": 0.976}     # #F1F5F9
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}      # #CBD5E1
# ========================================

def main():
    try:
        print(f"🔐 認証情報を読み込み中: {SERVICE_ACCOUNT_FILE}")
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)

        # 1. シートIDの取得
        print(f"🔍 シート '{SHEET_NAME}' のIDを検索中...")
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

        print(f"✅ シート発見: ID = {sheet_id}")

        # 2. データ範囲の確認 (デバッグ用)
        val_resp = service.spreadsheets().values().get(
            spreadsheetId=SSID, range=f"'{SHEET_NAME}'"
        ).execute()
        values = val_resp.get('values', [])
        actual_rows = len(values)
        actual_cols = len(values[0]) if actual_rows > 0 else 0
        print(f"📊 検出されたデータ範囲: {actual_rows}行 x {actual_cols}列")

        # 強制適用範囲 (データが少なくても最低限適用する)
        row_limit = max(actual_rows, 100)
        col_limit = max(actual_cols, 26) # Z列まで
        print(f"🛠 デザイン適用範囲: A1 から {chr(64+col_limit if col_limit <= 26 else 'Z')}{row_limit} まで")

        requests = []

        # --- A. ヘッダーのデザイン (1行目) ---
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": col_limit},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_HEADER_BG,
                        "textFormat": {"foregroundColor": COLOR_HEADER_TEXT, "bold": True},
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # --- B. 交互色の適用 (ストライプ) ---
        # 手動で1行おきに色を塗る (確実な方法)
        for r in range(1, row_limit, 2):
            requests.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": 0, "endColumnIndex": col_limit},
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": COLOR_ALT_ROW
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor)"
                }
            })

        # --- C. 枠線の適用 (全体) ---
        requests.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": row_limit, "startColumnIndex": 0, "endColumnIndex": col_limit},
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

        # --- D. 1行目の固定 ---
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1}
                },
                "fields": "gridProperties.frozenRowCount"
            }
        })

        # --- E. 列幅の自動調整 ---
        requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": col_limit
                }
            }
        })

        # まとめて実行
        print("🚀 APIリクエストを送信中...")
        service.spreadsheets().batchUpdate(
            spreadsheetId=SSID,
            body={'requests': requests}
        ).execute()

        print("✅ デザインの適用に成功しました！ブラウザを更新して確認してください。")

    except Exception as e:
        print(f"❌ エラー発生: {e}")

if __name__ == '__main__':
    main()
