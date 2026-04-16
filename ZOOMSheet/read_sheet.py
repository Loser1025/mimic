import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 設定
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_ID = '1YXES6PFY1feRXdAE_9WlUCEE22nWgkFEGCXaZDIZHrg'

def main():
    try:
        # 認証
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
        service = build('sheets', 'v4', credentials=creds)

        # 1. 全シートの情報を取得して最初のシート名を確認
        spreadsheet = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = spreadsheet.get('sheets', [])
        if not sheets:
            print('No sheets found.')
            return
        
        first_sheet_name = sheets[0].get('properties', {}).get('title')
        print(f"Using sheet: {first_sheet_name}")

        # 2. 正しいシート名でデータを取得 (A1:C200)
        range_name = f"'{first_sheet_name}'!A1:C200"
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get('values', [])

        if not values:
            print('No data found.')
            return

        # ヘッダーを除いて、Raw Response が含まれる行だけを表示
        print("\n--- Found Raw Responses ---")
        for row in values[1:]:
            if len(row) >= 2 and 'Raw Response' in row[1]:
                print(f"Queue: {row[0]} | Response: {row[1]}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
