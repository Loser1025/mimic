import os
import json
import urllib.parse
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# 設定情報
# ==========================================
# 認証ファイルパス
KEY_PATH = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'
# スプレッドシートID
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
# 対象シート名
SHEET_NAME = 'WEB/シミュ2'

# モダンカラーパレット (Slate-Indigo)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}  # Slate-800
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} # Slate-50
COLOR_ALT_BG = {"red": 0.941, "green": 0.961, "blue": 0.976}    # Slate-100
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}    # Slate-300

def main():
    print(f"🚀 デザイン適用を開始します: {SHEET_NAME}")

    try:
        # 1. 認証
        creds = service_account.Credentials.from_service_account_file(
            KEY_PATH, scopes=['https://www.googleapis.com/auth/spreadsheets']
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
            print(f"❌ シート '{SHEET_NAME}' が見つかりませんでした。")
            return

        # 3. データ範囲の取得 (デザイン適用範囲の決定)
        # シート名に特殊文字があるためシングルクォートで囲む
        range_name = f"'{SHEET_NAME}'"
        result = service.spreadsheets().values().get(
            spreadsheetId=SSID, range=range_name
        ).execute()
        values = result.get('values', [])

        if not values:
            print("❌ データが見つかりませんでした。")
            return

        row_count = len(values)
        col_count = len(values[0]) if row_count > 0 else 0
        print(f"📊 適用範囲: {row_count}行 x {col_count}列")

        # 4. 書式設定のリクエスト作成
        requests = []

        # --- A. ヘッダーのデザイン ---
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0, "endRowIndex": 1,
                    "startColumnIndex": 0, "endColumnIndex": col_count
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_HEADER_BG,
                        "textFormat": {
                            "foregroundColor": COLOR_HEADER_TEXT,
                            "bold": True,
                            "fontSize": 11
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE"
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
            }
        })

        # --- B. 縞々（ストライプ）背景色の適用 ---
        # 2行目以降、偶数行に淡い色を適用
        for r in range(1, row_count, 2):
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": r, "endRowIndex": r + 1,
                        "startColumnIndex": 0, "endColumnIndex": col_count
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": COLOR_ALT_BG
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })

        # --- C. 全体の枠線 (Borders) ---
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0, "endRowIndex": row_count,
                    "startColumnIndex": 0, "endColumnIndex": col_count
                },
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

        # --- D. 固定行の設定 (1行目を固定) ---
        requests.append({
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0, "endRowIndex": row_count,
                        "startColumnIndex": 0, "endColumnIndex": col_count
                    }
                }
            }
        }) # フィルターをかけることで利便性を向上

        # 凍結設定 (別API)
        service.spreadsheets().batchUpdate(
            spreadsheetId=SSID,
            body={"requests": [{"setBasicFilter": {"filter": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": row_count, "startColumnIndex": 0, "endColumnIndex": col_count}}}}]}
        ).execute()
        
        # 実際には freeze は updateSheetProperties で行う
        service.spreadsheets().batchUpdate(
            spreadsheetId=SSID,
            body={"requests": [{
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1}
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            }]}
        ).execute()

        # --- E. 列幅の自動調整 ---
        requests.append({
            "autoResizeColumns": {
                "range": {
                    "sheetId": sheet_id,
                    "startColumnIndex": 0, "endColumnIndex": col_count
                },
                "dimensions": "AT_LEAST_ONE"
            }
        })

        # まとめて実行
        service.spreadsheets().batchUpdate(
            spreadsheetId=SSID,
            body={"requests": requests}
        ).execute()

        print("✅ デザインの適用が完了しました！スプレッドシートを確認してください。")

    except Exception as e:
        print(f"❌ エラー発生: {e}")

if __name__ == '__main__':
    main()
