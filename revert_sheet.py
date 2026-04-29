import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# 認証情報のパス
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
            print("Authentication failed. Please check token.json")
            return

    service = build('sheets', 'v4', credentials=creds)

    # 1. シートのメタデータを取得
    spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet = next((s for s in spreadsheet['sheets'] if s['properties']['title'] == SHEET_NAME), None)
    
    if not sheet:
        print(f"Sheet '{SHEET_NAME}' not found.")
        return

    sheet_id = sheet['properties']['sheetId']
    row_count = sheet['properties']['gridProperties']['rowCount']
    col_count = sheet['properties']['gridProperties']['columnCount']

    # 16行目 (Index 15) 以降をリセット
    start_row = 15 
    
    requests = []

    # A. 背景色と配置をリセット (白・左揃え)
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": row_count,
                "startColumnIndex": 0,
                "endColumnIndex": col_count
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                    "horizontalAlignment": "LEFT",
                    "verticalAlignment": "BOTTOM"
                }
            },
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment)"
        }
    })

    # B. 罫線を削除
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": row_count,
                "startColumnIndex": 0,
                "endColumnIndex": col_count
            },
            "cell": {
                "userEnteredFormat": {
                    "borders": {
                        "top": {"style": "NONE"},
                        "bottom": {"style": "NONE"},
                        "left": {"style": "NONE"},
                        "right": {"style": "NONE"},
                    }
                }
            },
            "fields": "userEnteredFormat.borders"
        }
    })

    # 実行
    body = {'requests': requests}
    service.spreadsheets().batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body).execute()
    print(f"Successfully reverted formatting from row 16 onwards (Index {start_row}).")

if __name__ == '__main__':
    main()
