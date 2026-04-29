import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# 認証情報のパス
TOKEN_FILE = r'C:\Users\Loser\Desktop\-\-\nurse_list_deploy\token.json'
SPREADSHEET_ID = '1Mqq4gb0erNC6H3NPKvvorEaVgFxwdOB-EBxnYb4zru4'

def main():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)

    if not creds or not creds.valid:
        print("Invalid or missing token.")
        return

    try:
        service = build('sheets', 'v4', credentials=creds)
        # スプレッドシートの基本情報を取得
        spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        print(f"Spreadsheet Title: {spreadsheet.get('properties', {}).get('title')}")
        sheets = spreadsheet.get('sheets', [])
        for s in sheets:
            print(f"Sheet Title: {s.get('properties', {}).get('title')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
