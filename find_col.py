import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
SPREADSHEET_ID = '1hCyptQhLnuKJU3rTa7dcT0VoGPejXfGW40dVqHSHrlQ'
SHEET_NAME = 'クレスタ'

def main():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        print("Error: Credentials not valid.")
        return

    try:
        service = build('sheets', 'v4', credentials=creds)
        # Read Row 4 specifically
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"'{SHEET_NAME}'!A4:Z4"
        ).execute()
        values = result.get('values', [])
        if values:
            header = values[0]
            for i, col_name in enumerate(header):
                print(f"Col {chr(65+i)} ({i}): {col_name}")
        else:
            print("No header found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
