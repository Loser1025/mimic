import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

# 設定
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_ID = '1YXES6PFY1feRXdAE_9WlUCEE22nWgkFEGCXaZDIZHrg'
RANGE_NAME = 'Sheet1!A1:C200'  # 最初のシートの A1 から C200 まで取得

def main():
    try:
        # 認証
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly'])
        service = build('sheets', 'v4', credentials=creds)

        # データ取得
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        if not values:
            print('No data found.')
            return

        # ヘッダーを除いて、Raw Response が含まれる行だけを表示
        for row in values[1:]:
            if len(row) >= 2 and 'Raw Response' in row[1]:
                print(f"Queue: {row[0]} | Response: {row[1]}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
