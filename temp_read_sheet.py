import gspread
from google.oauth2.service_account import Credentials
import json

# Path to the service account key file
SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\tamalabo\csv-to-sheet\sa_credentials.json'

# Define the scope
scopes = ['https://www.googleapis.com/auth/spreadsheets']

# Credentials
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)

# Authorize
client = gspread.authorize(creds)

# Open the spreadsheet by URL
spreadsheet_url = 'https://docs.google.com/spreadsheets/d/13cK3BhIxFot0cZilbDHa4dzZoH_tocmNYWEk-pTnkJo/edit?gid=0#gid=0'
# Extract the spreadsheet ID from the URL
import re
match = re.search(r'/d/([a-zA-Z0-9-_]+)', spreadsheet_url)
if match:
    spreadsheet_id = match.group(1)
else:
    raise ValueError('Could not extract spreadsheet ID from URL')

sh = client.open_by_key(spreadsheet_id)

# Open worksheet named "保留"
try:
    worksheet = sh.worksheet('保留')
except gspread.exceptions.WorksheetNotFound:
    # Maybe the sheet name is in Japanese but with different encoding? Let's list all worksheets
    print('Worksheets:', [ws.title for ws in sh.worksheets()])
    raise

# Get all values
values = worksheet.get_all_values()
print(f'Sheet dimensions: {len(values)} rows x {len(values[0]) if values else 0} columns')
print('First 5 rows:')
for i, row in enumerate(values[:5]):
    print(f'Row {i}: {row}')
# Also print column headers if any
if values:
    headers = values[0]
    print('Headers:', headers)
    # Find index of columns U and V (0-based: U is 20, V is 21)
    if len(headers) >= 21:
        print(f'Column U (index 20) header: {headers[20] if len(headers) > 20 else "N/A"}')
        print(f'Column V (index 21) header: {headers[21] if len(headers) > 21 else "N/A"}')
    # Also check for a column named UV
    for idx, h in enumerate(headers):
        if h.strip().upper() == 'UV':
            print(f'Found column named UV at index {idx} (column {chr(65+idx)})')