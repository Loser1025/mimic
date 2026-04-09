import os
import json
import subprocess
import sys

# 依存ライブラリの確認とインストール
def install_dependencies():
    try:
        import google.oauth2.service_account
        import googleapiclient.discovery
    except ImportError:
        print("📦 必要なライブラリをインストールしています...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-auth", "google-api-python-client"])
        print("✅ インストール完了。再起動して実行します。")
        subprocess.call([sys.executable] + sys.argv)
        sys.exit()

install_dependencies()

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ================= 設定 =================
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_ID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'

# モダンカラーパレット (Slate-Indigo)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}      # #1E293B (Slate 800)
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98}   # #F8FAFC (Slate 50)
COLOR_ALT_ROW = {"red": 0.941, "green": 0.961, "blue": 0.976}      # #F1F5F9 (Slate 100)
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}       # #CBD5E1 (Slate 300)
# ========================================

def main():
    print(f"🚀 デザイン適用を開始します: {SHEET_NAME}")
    
    # 認証
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets']
    )
    service = build('sheets', 'v4', credentials=creds)

    # 1. シートIDの取得
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_id = None
    for s in spreadsheet['sheets']:
        if s['properties']['title'] == SHEET_NAME:
            sheet_id = s['properties']['sheetId']
            break
    
    if sheet_id is None:
        print(f"❌ シート '{SHEET_NAME}' が見つかりませんでした。")
        return

    # 2. データ範囲の取得 (行数・列数を判定)
    # シート名に特殊文字があるため、クォートして指定
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, 
        range=f"'{SHEET_NAME}'"
    ).execute()
    
    values = result.get('values', [])
    if not values:
        print("❌ データが見つかりませんでした。")
        return
    
    row_count = len(values)
    col_count = len(values[0])
    print(f"📊 範囲を検出しました: {row_count}行 x {col_count}列")

    # 3. デザインリクエストの構築
    requests = []

    # --- (A) ヘッダーのデザイン (1行目) ---
    requests.append({
        "repeatCell": {
            "range": { "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": col_count },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": COLOR_HEADER_BG,
                    "textFormat": { "foregroundColor": COLOR_HEADER_TEXT, "bold": True, "fontSize": 11 },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
        }
    })

    # --- (B) 全体の枠線 ---
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

    # --- (C) ストライプ（交互色）の設定 ---
    # Google API では repeatCell で行ごとに色を変えるのが一般的
    for r in range(1, row_count):
        if r % 2 == 0: # 偶数行に色を付ける
            requests.append({
                "repeatCell": {
                    "range": { "sheetId": sheet_id, "startRowIndex": r, "endRowIndex": r + 1, "startColumnIndex": 0, "endColumnIndex": col_count },
                    "cell": {
                        "userEnteredFormat": { "backgroundColor": COLOR_ALT_ROW }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })

    # --- (D) 1行目を固定 ---
    requests.append({
        "setBasicFilter": {
            "filter": {
                "range": { "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": row_count, "startColumnIndex": 0, "endColumnIndex": col_count }
            }
        }
    })
    # 注: 固定（Freeze）は別のAPIメソッドですが、batchUpdateの固定機能で実装可能
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": { "frozenRowCount": 1 }
            },
            "fields": "gridProperties.frozenRowCount"
        }
    })

    # --- (E) 列幅の自動調整 ---
    requests.append({
        "autoResizeColumns": {
            "range": { "sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": col_count }
        }
    })

    # 4. 一括実行
    body = {'requests': requests}
    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()
    
    print("✨ デザインの適用が完了しました！シートを確認してください。")

if __name__ == '__main__':
    main()
