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
        print("Error: Credentials not valid. Please re-authenticate.")
        return

    try:
        service = build('sheets', 'v4', credentials=creds)
        # Read the first 5 rows to see header and data
        result = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID, 
            range=f"'{SHEET_NAME}'!A1:Z5"
        ).execute()
        values = result.get('values', [])
        if not values:
            print("No data found.")
            return
        
        for i, row in enumerate(values):
            print(f"Row {i+1}: {row}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
