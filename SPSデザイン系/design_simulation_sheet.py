import json
import urllib.request
import urllib.parse
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ==========================================
# 設定
# ==========================================
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'

# カラーパレット (RGB 0.0 ~ 1.0)
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231}  # Slate-800
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} # Slate-50
COLOR_STRIPE_BG = {"red": 0.95, "green": 0.96, "blue": 0.98}      # Very light blue/slate
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882}      # Slate-300

# ステータス色
COLOR_OK = {"red": 0.85, "green": 0.95, "blue": 0.85}    # 淡い緑
COLOR_NG = {"red": 0.95, "green": 0.85, "blue": 0.85}    # 淡い赤
COLOR_PENDING = {"red": 0.98, "green": 0.98, "blue": 0.85} # 淡い黄

def main():
    print("🚀 スマートデザイン適用を開始します...")
    
    # 1. 認証
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        service = build('sheets', 'v4', credentials=creds)
    except Exception as e:
        print(f"❌ 認証エラー: {e}")
        return

    # 2. シートIDの取得
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=SSID).execute()
        sheet_id = next(s['properties']['sheetId'] for s in spreadsheet['sheets'] if s['properties']['title'] == SHEET_NAME)
        print(f"✅ シートが見つかりました: {SHEET_NAME} (ID: {sheet_id})")
    except Exception as e:
        print(f"❌ シート取得エラー: {e}")
        return

    # 3. データ範囲の確認
    try:
        val_resp = service.spreadsheets().values().get(
            spreadsheetId=SSID, range=f"'{SHEET_NAME}'"
        ).execute()
        values = val_resp.get('values', [])
        row_count = len(values)
        col_count = len(values[0]) if row_count > 0 else 10
        print(f"📊 データ範囲を検出: {row_count}行 x {col_count}列")
    except Exception as e:
        print(f"⚠️ データ取得に失敗しましたが、デフォルト範囲で適用します: {e}")
        row_count, col_count = 100, 26

    # 4. デザインリクエストの構築
    requests = []

    # --- (A) 1行目の固定 ---
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1}
            },
            "fields": "gridProperties.frozenRowCount"
        }
    })

    # --- (B) ヘッダーのデザイン (1行目) ---
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
                        "bold": True
                    },
                    "horizontalAlignment": "CENTER"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }
    })

    # --- (C) 全体の枠線 ---
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0, "endRowIndex": row_count if row_count > 0 else 100,
                "startColumnIndex": 0, "endColumnIndex": col_count if col_count > 0 else 26
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

    # --- (D) 列幅の自動調整 ---
    requests.append({
        "autoResizeDimensions": {
            "dimensions": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": 0,
                "endIndex": col_count if col_count > 0 else 26
            }
        }
    })

    # 5. 条件付き書式の設定 (Dynamic Coloring)
    # 注: 条件付き書式は batchUpdate ではなく addConditionalFormatRule を使う
    rules = []
    
    # 縞々（ストライプ）行の設定 (偶数行に色付け)
    rules.append({
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 1, "endRowIndex": row_count if row_count > 0 else 100,
            "startColumnIndex": 0, "endColumnIndex": col_count if col_count > 0 else 26
        },
        "booleanRule": {
            "condition": {
                "type": "CUSTOM_FORMULA",
                "values": [{"userEnteredValue": "=ISEVEN(ROW())"}]
            },
            "format": {
                "backgroundColor": COLOR_STRIPE_BG
            }
        }
    })

    # ステータス色: OK/完了/達成 -> 緑
    rules.append({
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 1, "endRowIndex": row_count if row_count > 0 else 100,
            "startColumnIndex": 0, "endColumnIndex": col_count if col_count > 0 else 26
        },
        "booleanRule": {
            "condition": {
                "type": "TEXT_CONTAINS",
                "values": [{"userEnteredValue": "OK"}]
            },
            "format": {"backgroundColor": COLOR_OK}
        }
    })
    # ステータス色: NG/未完了/未達 -> 赤
    rules.append({
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 1, "endRowIndex": row_count if row_count > 0 else 100,
            "startColumnIndex": 0, "endColumnIndex": col_count if col_count > 0 else 26
        },
        "booleanRule": {
            "condition": {
                "type": "TEXT_CONTAINS",
                "values": [{"userEnteredValue": "NG"}]
            },
            "format": {"backgroundColor": COLOR_NG}
        }
    })
    # ステータス色: 保留/注意/Pending -> 黄
    rules.append({
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 1, "endRowIndex": row_count if row_count > 0 else 100,
            "startColumnIndex": 0, "endColumnIndex": col_count if col_count > 0 else 26
        },
        "booleanRule": {
            "condition": {
                "type": "TEXT_CONTAINS",
                "values": [{"userEnteredValue": "保留"}]
            },
            "format": {"backgroundColor": COLOR_PENDING}
        }
    })

    # 6. 実行
    try:
        # 基本デザインの適用
        service.spreadsheets().batchUpdate(
            spreadsheetId=SSID,
            body={'requests': requests}
        ).execute()

        # 条件付き書式の適用
        service.spreadsheets().batchUpdate(
            spreadsheetId=SSID,
            body={'requests': [{'addConditionalFormatRule': {'rule': r, 'sheetId': sheet_id}} for r in rules]}
        ).execute()

        print("\n✅ スマートデザインの適用に成功しました！")
        print("✨ 以下の機能が有効になりました：")
        print("  - モダンな Slate-Indigo ヘッダー")
        print("  - データの自動読み取りに基づくストライプ行")
        print("  - 文字（OK/NG/保留）に連動する自動色付け")
        print("  - 自動列幅調整 ＆ 1行目固定")
        print("\nブラウザをリロードして確認してください。")

    except Exception as e:
        print(f"❌ デザイン適用エラー: {e}")

if __name__ == '__main__':
    main()
