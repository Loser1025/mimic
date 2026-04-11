import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# スプレッドシート読み取り用の権限スコープ
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# ユーザー指定のシート情報
SPREADSHEET_ID = '1hCyptQhLnuKJU3rTa7dcT0VoGPejXfGW40dVqHSHrlQ'
TARGET_GID = '821712399'

def main():
    creds = None
    # token.jsonを確認
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 権限が不足している、または有効でない場合は再認証
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('client_secret.json'):
                print("エラー: 'client_secret.json' が見つかりません。")
                return
            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('sheets', 'v4', credentials=creds)
        
        # 1. GIDからシート名を探す
        spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = spreadsheet.get('sheets', [])
        sheet_name = None
        for s in sheets:
            if str(s.get('properties', {}).get('sheetId')) == TARGET_GID:
                sheet_name = s.get('properties', {}).get('title')
                break
        
        if not sheet_name:
            print(f"エラー: GID {TARGET_GID} に一致するシートが見つかりませんでした。")
            return

        print(f"シート '{sheet_name}' のデータを読み取ります...")

        # 2. データの読み取り (A1:Z100 の範囲を適当に取得)
        range_name = f"'{sheet_name}'!A1:Z100"
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=range_name
        ).execute()
        
        values = result.get('values', [])

        if not values:
            print('データが見つかりませんでした。')
        else:
            print('\n--- シート内容 (先頭100行) ---')
            for row in values:
                print(row)
            print('----------------------------')

    except Exception as e:
        print(f"APIエラーが発生しました: {e}")
        print("権限エラーが出た場合は、一度 'token.json' を削除して再実行してください。")

if __name__ == '__main__':
    main()
