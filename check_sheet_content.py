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

    # シートの内容を取得
    try:
        range_name = f"'{SHEET_NAME}'!A1:Z100"
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=range_name
        ).execute()
        
        values = result.get('values', [])

        if not values:
            print('No data found.')
        else:
            print(f'Data found in sheet "{SHEET_NAME}":')
            for i, row in enumerate(values):
                print(f'Row {i+1}: {row}')
    except Exception as e:
        print(f"Error occurred: {e}")

if __name__ == '__main__':
    main()
