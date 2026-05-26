import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1
import json

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

# Get all values to determine rows and columns
values = worksheet.get_all_values()
if not values:
    print('No data')
    exit()

num_rows = len(values)
num_cols = len(values[0]) if values else 0
print(f'Sheet: {num_rows} rows, {num_cols} columns')

# We'll format columns U (index 20) and V (index 21)
col_u_index = 20  # 0-based
col_v_index = 21

# Define colors (as fractions of 255)
# Light blue for column U labels
color_blue = {'red': 0.86, 'green': 0.90, 'blue': 0.95}  # #DCE6F1 approx
# Light green for positive numbers in V
color_green = {'red': 0.84, 'green': 0.91, 'blue': 0.83}  # #D5E8D4
# Light yellow for zero in V
color_yellow = {'red': 1.0, 'green': 0.95, 'blue': 0.8}   # #FFF2CC
# Light gray for other non-empty in V
color_gray = {'red': 0.92, 'green': 0.92, 'blue': 0.92}   # #EAEAEA

# Prepare format requests
requests = []

# Helper to add a format request for a range
def add_format_request(start_row, end_row, start_col, end_col, color):
    # Convert to A1 notation
    start_a1 = rowcol_to_a1(start_row + 1, start_col + 1)  # rows and cols are 1-based in A1
    end_a1 = rowcol_to_a1(end_row + 1, end_col + 1)
    # If single cell, end_a1 same as start_a1? Actually we want range like "U2:U5"
    # gspread's batch_update expects a gridRange.
    # We'll construct using gridRange directly.
    request = {
        "repeatCell": {
            "range": {
                "sheetId": worksheet.id,
                "startRowIndex": start_row,
                "endRowIndex": end_row + 1,  # end exclusive
                "startColumnIndex": start_col,
                "endColumnIndex": end_col + 1,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": color
                }
            },
            "fields": "userEnteredFormat.backgroundColor"
        }
    }
    requests.append(request)

# Process each row
for r in range(num_rows):
    # Column U
    u_val = values[r][col_u_index] if len(values[r]) > col_u_index else ''
    if u_val.strip() != '':
        # Non-empty in U: apply light blue
        add_format_request(r, r, col_u_index, col_u_index, color_blue)
    # Column V
    v_val = values[r][col_v_index] if len(values[r]) > col_v_index else ''
    if v_val.strip() != '':
        # Try to parse as number
        try:
            num = float(v_val)
            if num > 0:
                color = color_green
            else:
                color = color_yellow
        except ValueError:
            # Not a number
            color = color_gray
        add_format_request(r, r, col_v_index, col_v_index, color)

# If there are requests, batch update
if requests:
    body = {
        "requests": requests
    }
    response = worksheet.spreadsheet.batch_update(body)
    print(f'Applied formatting to {len(requests)} cells.')
else:
    print('No formatting applied (no data in U or V columns).')

print('Done.')