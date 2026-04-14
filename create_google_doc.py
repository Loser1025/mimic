import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# Scopes for Drive and Docs API
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate():
    creds = None
    token_path = 'token.json'
    secret_path = 'client_secret.json'
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
            # Since we are in a non-interactive environment, this might fail if token is missing.
            # But we have token.json, so it should work.
            creds = flow.run_local_server(port=0)
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    
    return creds

def markdown_to_html(md_text):
    lines = md_text.split('\n')
    html = ["<html><body>"]
    in_table = False
    
    for line in lines:
        line = line.strip()
        if not line:
            if in_table:
                html.append("</table>")
                in_table = False
            html.append("<br>")
            continue
            
        # Table handling
        if line.startswith('|'):
            if not in_table:
                html.append("<table>")
                in_table = True
            
            # Skip separator rows like | --- | --- |
            if '---' in line and not any(c.isalpha() or c.isdigit() for c in line.replace('|', '').replace('-', '')):
                continue
                
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            html.append("<tr>")
            for cell in cells:
                # Handle bold inside cells
                cell_html = cell.replace('**', '<b>', 1).replace('**', '</b>', 1) if cell.count('**') == 2 else cell
                html.append(f"<td>{cell_html}</td>")
            html.append("</tr>")
            continue
        else:
            if in_table:
                html.append("</table>")
                in_table = False
        
        # Headers
        if line.startswith('# '):
            html.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith('## '):
            html.append(f"<h2>{line[3:]}</h2>")
        # Lists
        elif line.startswith('- '):
            html.append(f"<li>{line[2:].replace('**', '<b>', 1).replace('**', '</b>', 1) if line.count('**') == 2 else line[2:]}</li>")
        # Paragraphs
        else:
            p_text = line.replace('**', '<b>', 1).replace('**', '</b>', 1) if line.count('**') == 2 else line
            html.append(f"<p>{p_text}</p>")
            
    if in_table:
        html.append("</table>")
        
    html.append("</body></html>")
    return "\n".join(html)

def create_doc(text):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)
    
    html_content = markdown_to_html(text)
    
    file_metadata = {
        'name': '【報告書】入電経路誤認による案件取り違えの経緯',
        'mimeType': 'application/vnd.google-apps.document'
    }
    
    media = MediaIoBaseUpload(
        io.BytesIO(html_content.encode('utf-8')), 
        mimetype='text/html', 
        resumable=True
    )
    
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

if __name__ == '__main__':
    with open('じゆうちょう.md', 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        doc_id = create_doc(content)
        print(f"SUCCESS: Document created with ID: {doc_id}")
        print(f"URL: https://docs.google.com/document/d/{doc_id}/edit")
    except Exception as e:
        print(f"FAILURE: {str(e)}")
