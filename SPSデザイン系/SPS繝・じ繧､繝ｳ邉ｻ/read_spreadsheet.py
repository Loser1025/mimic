import gspread
from google.oauth2.service_account import Credentials
import traceback

# Configuration
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json'
SPREADSHEET_ID = '1hCyptQhLnuKJU3rTa7dcT0VoGPejXfGW40dVqHSHrlQ'
TARGET_GID = 821712399

# Define the scope
SCOPE = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

try:
    # Authenticate
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPE)
    gc = gspread.authorize(creds)

    # Open the spreadsheet
    sh = gc.open_by_key(SPREADSHEET_ID)

    # Find the worksheet by GID
    worksheet = None
    for ws in sh.worksheets():
        if ws.id == TARGET_GID:
            worksheet = ws
            break

    if worksheet is None:
        # Try to get the first worksheet if GID is not found
        print(f"Worksheet with GID {TARGET_GID} not found. Using the first worksheet.")
        worksheet = sh.get_worksheet(0)

    # Read all values
    data = worksheet.get_all_values()

    if not data:
        print("The worksheet is empty.")
    else:
        # Print data in a readable format
        for row in data:
            print('\t'.join(row))

except Exception as e:
    print(f"An error occurred: {e}")
    traceback.print_exc()
