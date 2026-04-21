import json
import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

PRESENTATION_ID = "1eCYXBpheJttHWb2zkCC2Op_NOijdcCMs8dqbzDN5jcc"
TOKEN_PATH = r"C:\Users\Loser\Desktop\-\-\反響貼付sp報告用\token.json"
CLIENT_SECRET_PATH = r"C:\Users\Loser\Desktop\-\-\反響貼付sp報告用\credentials.json"

with open(TOKEN_PATH) as f:
    token_data = json.load(f)

with open(CLIENT_SECRET_PATH) as f:
    client_data = json.load(f)["installed"]

scopes = token_data.get("scopes", ["https://www.googleapis.com/auth/drive"])
creds = Credentials(
    token=token_data.get("token"),
    refresh_token=token_data["refresh_token"],
    token_uri=token_data["token_uri"],
    client_id=token_data["client_id"],
    client_secret=token_data["client_secret"],
    scopes=scopes,
)

if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    token_data["token"] = creds.token
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_data, f)
    print("Token refreshed.")

service = build("slides", "v1", credentials=creds)
presentation = service.presentations().get(presentationId=PRESENTATION_ID).execute()

slides = presentation.get("slides", [])
print(f"Total slides: {len(slides)}\n")

for i, slide in enumerate(slides):
    slide_id = slide["objectId"]
    print(f"--- Slide {i+1} (ID: {slide_id}) ---")
    for element in slide.get("pageElements", []):
        shape = element.get("shape", {})
        text_content = shape.get("text", {})
        if text_content:
            full_text = ""
            for tr in text_content.get("textRuns", []):
                full_text += tr.get("content", "")
            if full_text.strip():
                print(f"  Text: {repr(full_text.strip()[:200])}")

    # Check speaker notes
    notes_page = slide.get("slideProperties", {}).get("notesPage", {})
    for element in notes_page.get("pageElements", []):
        shape = element.get("shape", {})
        text_content = shape.get("text", {})
        if text_content:
            runs = text_content.get("textRuns", [])
            note_text = "".join(r.get("content", "") for r in runs).strip()
            if note_text:
                print(f"  Notes: {repr(note_text[:100])}")
    print()
