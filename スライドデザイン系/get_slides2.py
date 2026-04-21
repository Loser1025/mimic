import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

PRESENTATION_ID = "1eCYXBpheJttHWb2zkCC2Op_NOijdcCMs8dqbzDN5jcc"
TOKEN_PATH = r"C:\Users\Loser\Desktop\-\-\反響貼付sp報告用\token.json"

with open(TOKEN_PATH) as f:
    token_data = json.load(f)

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

service = build("slides", "v1", credentials=creds)
presentation = service.presentations().get(presentationId=PRESENTATION_ID).execute()
slides = presentation.get("slides", [])
print(f"Total slides: {len(slides)}\n")

def extract_text(page_elements):
    texts = []
    for el in page_elements:
        shape = el.get("shape", {})
        text_obj = shape.get("text", {})
        elements = text_obj.get("textElements", [])
        full = ""
        for te in elements:
            tr = te.get("textRun", {})
            full += tr.get("content", "")
        if full.strip():
            texts.append(full.strip())
    return texts

for i, slide in enumerate(slides):
    slide_id = slide["objectId"]
    print(f"=== Slide {i+1} (ID: {slide_id}) ===")
    texts = extract_text(slide.get("pageElements", []))
    for t in texts:
        print(f"  [{t[:300]}]")

    # Speaker notes
    notes_page = slide.get("slideProperties", {}).get("notesPage", {})
    note_texts = extract_text(notes_page.get("pageElements", []))
    for nt in note_texts:
        if nt.strip():
            print(f"  NOTE: [{nt[:200]}]")
    print()
