"""
Google Slides 構造確認スクリプト
プレゼンテーションのスライドID・タイトル・現在のノートを一覧表示する
"""

from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY_PATH = r"C:/Users/弁護士法人響/Downloads/ageless-impulse-488713-m6-0c52b81add54.json"
PRESENTATION_ID = "1P0IbvKlfcIZxV8SdptlYVfHV-hSP_Mluf2iiQFVa23Q"
SCOPES = ["https://www.googleapis.com/auth/presentations.readonly"]

creds = service_account.Credentials.from_service_account_file(SA_KEY_PATH, scopes=SCOPES)
service = build("slides", "v1", credentials=creds)

presentation = service.presentations().get(presentationId=PRESENTATION_ID).execute()
slides = presentation.get("slides", [])

print(f"スライド総数: {len(slides)}\n")
print("=" * 60)

for i, slide in enumerate(slides, 1):
    slide_id = slide.get("objectId", "")

    # スライドのタイトルテキストを取得（あれば）
    title_text = ""
    for element in slide.get("pageElements", []):
        shape = element.get("shape", {})
        placeholder = shape.get("placeholder", {})
        if placeholder.get("type") == "TITLE":
            for para in shape.get("text", {}).get("textElements", []):
                tr = para.get("textRun", {})
                title_text += tr.get("content", "")
            break

    # ノートページのテキストを取得
    notes_text = ""
    notes_page = slide.get("slideProperties", {}).get("notesPage", {})
    for element in notes_page.get("pageElements", []):
        shape = element.get("shape", {})
        placeholder = shape.get("placeholder", {})
        if placeholder.get("type") == "BODY":
            for te in shape.get("text", {}).get("textElements", []):
                tr = te.get("textRun", {})
                notes_text += tr.get("content", "")

    title_display = title_text.strip().replace("\n", " ") or "（タイトルなし）"
    notes_preview = notes_text.strip()[:50].replace("\n", " ") if notes_text.strip() else "（ノートなし）"

    print(f"[{i:02d}] slide_id: {slide_id}")
    print(f"      タイトル : {title_display}")
    print(f"      ノート   : {notes_preview}")
    print()
