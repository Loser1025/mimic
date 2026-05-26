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

# Get all values
values = worksheet.get_all_values()
print(f'Total rows: {len(values)}')
if len(values) == 0:
    print('No data')
    exit()

# Determine number of columns
num_cols = len(values[0])
print(f'Number of columns: {num_cols}')
# Print header row
print('Header row:')
for i, header in enumerate(values[0]):
    print(f'  Col {i} ({chr(65+i)}): "{header}"')

# Now examine columns U (index 20) and V (index 21) if they exist
if num_cols > 20:
    print('\nColumn U (index 20, column U):')
    for i, row in enumerate(values):
        if len(row) > 20:
            val = row[20]
            if val.strip() != '':
                print(f'  Row {i}: "{val}"')
else:
    print('Column U does not exist (less than 21 columns)')

if num_cols > 21:
    print('\nColumn V (index 21, column V):')
    for i, row in enumerate(values):
        if len(row) > 21:
            val = row[21]
            if val.strip() != '':
                print(f'  Row {i}: "{val}"')
else:
    print('Column V does not exist (less than 22 columns)')

# Also, let's see what's in columns T, U, V, W, X for rows that have data in U or V
print('\n--- Detailed view for rows with non-empty U or V ---')
for i, row in enumerate(values):
    u_val = row[20] if len(row) > 20 else ''
    v_val = row[21] if len(row) > 21 else ''
    if u_val.strip() != '' or v_val.strip() != '':
        print(f'Row {i}:')
        for j in range(max(0, 20-2), min(num_cols, 21+3)):  # Show T-U-V-W-X (indices 19-23)
            col_letter = chr(65+j)
            cell_val = row[j] if j < len(row) else ''
            print(f'  Col {col_letter} (index {j}): "{cell_val}"')
        print()