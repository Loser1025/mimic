import json
import os
import urllib.request
import urllib.parse
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 設定 ---
SSID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'WEB/シミュ2'
JSON_KEY_PATH = r'C:\Users\Loser\Desktop\-\-\SPSデザイン系\ageless-impulse-488713-m6-03014b3cddad.json'

# --- カラーパレット (モダン Slate-Indigo) ---
COLOR_HEADER_BG = {"red": 0.117, "green": 0.165, "blue": 0.231} # Slate 800
COLOR_HEADER_TEXT = {"red": 0.972, "green": 0.976, "blue": 0.98} # Slate 50
COLOR_ALT_BG = {"red": 0.941, "green": 0.961, "blue": 0.976} # Slate 100
COLOR_BORDER = {"red": 0.796, "green": 0.835, "blue": 0.882} # Slate 300

# 条件付き書式用カラー
COLOR_SUCCESS_BG = {"red": 0.85, "green": 0.95, "blue": 0.85} # 淡い緑
COLOR_FAIL_BG = {"red": 0.95, "green": 0.85, "blue": 0.85}    # 淡い赤
COLOR_WARN_BG = {"red": 0.95, "green": 0.95, "blue": 0.85}    # 淡い黄

def main():
    print("🚀 スマートデザイン適用を開始します...")
    
    # 1. 認証
    try:
        creds = service_account.Credentials.from_service_account_file(
            JSON_KEY_PATH, scopes=['https://www.googleapis.com/auth/spreadsheets']
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
        val_resp = service.spreadsheets().values().get(spreadsheetId=SSID, range=f"'{SHEET_NAME}'").execute()
        values = val_resp.get('values', [])
        row_count = len(values)
        col_count = len(values[0]) if row_count > 0 else 0
        print(f"📊 検出されたデータ範囲: {row_count}行 x {col_count}列")
    except Exception as e:
        print(f"⚠️ データ取得に失敗しましたが、デフォルト範囲で適用します: {e}")
        row_count, col_count = 100, 26

    # 範囲の安全策（最低限の範囲を確保）
    end_row = max(row_count, 100)
    end_col = max(col_count, 26)

    # 4. リクエストの構築
    requests = []

    # A. ヘッダーデザイン (1行目)
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": end_col},
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

    # B. 全体枠線
    requests.append({
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": end_row, "startColumnIndex": 0, "endColumnIndex": end_col},
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

    # C. 行の固定 (1行目)
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1}
            },
            "fields": "gridProperties.frozenRowCount"
        }
    })

    # D. 列幅の自動調整
    requests.append({
        "autoResizeDimensions": {
            "dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": end_col}
        }
    })

    # E. 条件付き書式: ストライプ (偶数行を淡いグレーに)
    # ※Google APIのaddConditionalFormatRuleではカスタム数式を使ってストライプを実現
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": end_row, "startColumnIndex": 0, "endColumnIndex": end_col}],
                "booleanRule": {
                    "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=ISODD(ROW())"}]},
                    "format": {"backgroundColor": COLOR_ALT_BG}
                }
            },
            "index": 0
        }
    })

    # F. 条件付き書式: スマートカラーリング (キーワードベース)
    rules = [
        {"keywords": ["OK", "完了", "達成", "成功", "Yes"], "color": COLOR_SUCCESS_BG},
        {"keywords": ["NG", "未完了", "未達", "失敗", "No"], "color": COLOR_FAIL_BG},
        {"keywords": ["保留", "注意", "Pending", "確認中"], "color": COLOR_WARN_BG},
    ]

    for i, r in enumerate(rules):
        for kw in r["keywords"]:
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": end_row, "startColumnIndex": 0, "endColumnIndex": end_col}],
                        "booleanRule": {
                            "condition": {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": kw}]},
                            "format": {"backgroundColor": r["color"]}
                        }
                    },
                    "index": i + 1
                }
            })

    # 5. 一括適用
    try:
        body = {'requests': requests}
        service.spreadsheets().batchUpdate(spreadsheetId=SSID, body=body).execute()
        print(f"✅ デザインを適用しました！ (リクエスト数: {len(requests)})")
        print("✨ 今度はデータの中身に合わせて色が変わる『スマートデザイン』になっています。")
        print("👉 シートを確認して、'OK' や 'NG' と入力して色の変化を試してみてください！")
    except Exception as e:
        print(f"❌ API適用エラー: {e}")

if __name__ == '__main__':
    main()
