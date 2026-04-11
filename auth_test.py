import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 権限スコープ（Google Driveの読み取り専用）
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

def main():
    creds = None
    # token.jsonに前回の認証情報が保存されているか確認
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # 有効な認証情報がない場合はログインフローを開始
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('client_secret.json'):
                print("エラー: 'client_secret.json' が見つかりません。")
                print("Google Cloud Consoleからダウンロードしてこのフォルダに配置してください。")
                return

            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # 次回からログイン不要にするため保存
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('drive', 'v3', credentials=creds)
        # ファイルを10件だけ取得して表示
        results = service.files().list(pageSize=10, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            print('ファイルが見つかりませんでした。')
        else:
            print('Google Drive内のファイル一覧:')
            for item in items:
                print(f"{item['name']} ({item['id']})")
    except Exception as e:
        print(f"APIエラーが発生しました: {e}")

if __name__ == '__main__':
    main()
