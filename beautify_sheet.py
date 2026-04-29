import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 認証情報のパス
CLIENT_SECRET_FILE = r'C:\Users\Loser\Desktop\-\-\nurse_list_deploy\client_secret.json'
TOKEN_FILE = r'C:\Users\Loser\Desktop\-\-\nurse_list_deploy\token.json'
SPREADSHEET_ID = '1BJYhsb38mCtVOpHdfm-RUOdAiQyhIVTSP2qKP3nTeP0'
SHEET_NAME = 'りうにう'

def main():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, ['https://www.googleapis.com/auth/spreadsheets'])
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())

    service = build('sheets', 'v4', credentials=creds)

    # 1. シートのメタデータを取得して ID と範囲を確認
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet = next((s for s in spreadsheet['sheets'] if s['properties']['title'] == SHEET_NAME), None)
    
    if not sheet:
        print(f"Sheet '{SHEET_NAME}' not found.")
        return

    sheet_id = sheet['properties']['sheetId']
    row_count = sheet['properties']['gridProperties']['rowCount']
    col_count = sheet['properties']['gridProperties']['columnCount']

    print(f"Sheet ID: {sheet_id}, Rows: {row_count}, Cols: {col_count}")

    # 2. 書式設定リクエストの作成
    requests = []

    # A. 上位2行を固定
    requests.append({
        "setBasicFilter": { # これはフィルタなので不要。固定は updateSheetProperties
        }
    })
    # 修正: 固定は updateSheetProperties
    requests = [{
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": 2
                }
            },
            "fields": "gridProperties.frozenRowCount"
        }
    }]

    # B. ヘッダー (Row 0-1) の色とスタイル
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 2,
                "startColumnIndex": 0,
                "endColumnIndex": col_count
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47}, # #1f4e78
                    "textFormat": {
                        "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                        "bold": True
                    },
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)"
        }
    })

    # C. データ行 (Row 2+) のストライプ背景色 (交互)
    # 偶数行 (Row 2, 4, ...)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 2,
                "endRowIndex": row_count
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}, # White
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment)"
        }
    })
    
    # 奇数行 (Row 3, 5, ...) -> ここでストライプを適用
    # 注意: repeatCell で交互に塗ることはできないため、個別に指定するか-
    # 実際には API でストライプをやるには loop で request を作る
    for r in range(3, row_count, 2):
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": r,
                    "endRowIndex": r + 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": col_count
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}, # #f3f3f3
                    }
                },
                "fields": "userEnteredFormat(backgroundColor)"
            }
        })

    # D. B列 (Index 1) を左揃えに
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 2,
                "endRowIndex": row_count,
                "startColumnIndex": 1,
                "endColumnIndex": 2
            },
            "cell": {
                "userEnteredFormat": {
                    "horizontalAlignment": "LEFT"
                }
            },
            "fields": "userEnteredFormat(horizontalAlignment)"
        }
    })

    # E. 全体に罫線を適用
    requests.append({
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": row_count,
                "startColumnIndex": 0,
                "endColumnIndex": col_count
            },
            "rows": [
                {
                    "values": [
                        {
                            "userEnteredFormat": {
                                "borders": {
                                    "top": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                                    "bottom": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                                    "left": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                                    "right": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                                }
                            }
                        }
                    ]
                }
            ],
            "fields": "userEnteredFormat.borders"
        }
    })
    # 修正: updateCells は全セルを定義する必要があるため、罫線だけをやる場合は 
    # repeatCell ではなく、本当は updateCells で-
    # しかし、罫線を全セルに塗る簡単な方法は repeatCell ではできない。
    # 代わりに、外枠を太く、内側を細く設定するのが一般的。
    #-
    # 正しくは、repeatCell では罫線も設定可能。
    # 修正して repeatCell で罫線を設定する。

    # 罫線リクエストを repeatCell で再定義
    requests.pop() # 先ほどの updateCells を削除
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": row_count,
                "startColumnIndex": 0,
                "endColumnIndex": col_count
            },
            "cell": {
                "userEnteredFormat": {
                    "borders": {
                        "top": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                        "bottom": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                        "left": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                        "right": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                    }
                }
            },
            "fields": "userEnteredFormat.borders"
        }
    })

    # 3. 実行
    body = {
        'requests': requests
    }
    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()
    print("Successfully beautified the sheet!")

if __name__ == '__main__':
    main()
