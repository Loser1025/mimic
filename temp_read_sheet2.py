import gspread
from google.oauth2.service_account import Credentials

SERVICE_ACCOUNT_FILE = r'C:\Users\Loser\Desktop\-\tamalabo\csv-to-sheet\sa_credentials.json'
scopes = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
client = gspread.authorize(creds)

spreadsheet_url = 'https://docs.google.com/spreadsheets/d/13cK3BhIxFot0cZilbDHa4dzZoH_tocmNYWEk-pTnkJo/edit?gid=0#gid=0'
import re
match = re.search(r'/d/([a-zA-Z0-9-_]+)', spreadsheet_url)
spreadsheet_id = match.group(1)
sh = client.open_by_key(spreadsheet_id)
worksheet = sh.worksheet('保留')

values = worksheet.get_all_values()
print(f'Total rows: {len(values)}')
print('Examining columns U (index 20) and V (index 21):')
for i, row in enumerate(values):
    u_val = row[20] if len(row) > 20 else ''
    v_val = row[21] if len(row) > 21 else ''
    if u_val.strip() != '' or v_val.strip() != '':
        print(f'Row {i}: U=[{u_val}], V=[{v_val}]')
        # Also show first few columns for context
        context = ' '.join([str(cell) for cell in row[:5] if cell])
        if context:
            print(f'   Context: {context[:50]}')