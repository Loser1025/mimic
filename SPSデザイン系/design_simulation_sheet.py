import os
import json
import urllib.parse
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# 設定
# ==========================================
# 認証情報ファイルのパス
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'
# スプレッドシートID
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
# 対象シート名
SHEET_NAME = 'WEB/シミュ2'

# モダンデザイン・カラーパレット (RGB 0.0 ~ 1.0)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}    # Slate-800 (#1E293B)
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} # Slate-50 (#F8FAFC)
COLOR_ROW_ALT = {"red": 0.941, "green": 0.961, "blue": 0.976}    # Slate-100 (#F1F5F9)
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}    # Slate-300 (#CBD5E1)

def main():
    print(f"🚀 デザイン適用を開始します: {SHEET_NAME}")

    try:
        # 1. 認証とサービス構築
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)

        # 2. シートIDの取得
        spreadsheet = service.spreadsheets().get(spreadsheetId=SSID).execute()
        sheet_id = None
        for s in spreadsheet['sheets']:
            if s['properties']['title'] == SHEET_NAME:
                sheet_id = s['properties']['sheetId']
                break
        
        if sheet_id is None:
            print(f"❌ エラー: シート '{SHEET_NAME}' が見つかりませんでした。")
            return

        # 3. データ範囲の取得（サイズ決定のため）
        # シングルクォーテーションで囲んでエンコード
        range_name = f"'{SHEET_NAME}'"
        result = service.spreadsheets().values().get(
            spreadsheetId=SSID, range=range_name
        ).execute()
        values = result.get('values', [])

        if not values:
            print("⚠️ データが空のため、デザインを適用できません。")
            return

        row_count = len(values)
        col_count = len(values[0]) if row_count > 0 else 0

        # 4. バッチ更新リクエストの構築
        requests = []

        # --- ヘッダーのデザイン ---
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

        # --- 交互色の設定 (条件付き書式) ---
        # 偶数行に淡い色を適用
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": row_count, "startColumnIndex": 0, "endColumnIndex": col_count}],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": "=ISEVEN(ROW())"}]
                        },
                        "format": {
                            "backgroundColor": COLOR_ROW_ALT
                        }
                    }
                },
                "index": 0
            }
        })

        # --- 全体の枠線 (repeatCell) ---
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

        # --- 列幅の自動調整 ---
        requests.append({
            "autoResizeColumns": {
                "range": {
                    "sheetId": sheet_id,
                    "startColumnIndex": 0, "endColumnIndex": col_count
                },
                "options": "EXPAND"
            }
        })

        # --- ヘッダーの固定 ---
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
        })
        # 注: setBasicFilterの代わりに固定行を設定
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": 1
                    }
                },
                "fields": "gridProperties.frozenRowCount"
            }
        })

        # 一括実行
        body = {'requests': requests}
        service.spreadsheets().batchUpdate(spreadsheetId=SSID, body=body).execute()

        print(f"✅ 完了！シート '{SHEET_NAME}' にモダンデザインを適用しました。")

    except Exception as e:
        print(f"❌ エラー発生: {e}")

if __name__ == '__main__':
    main()
