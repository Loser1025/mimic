import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

def upload_to_google_sheets(data):
    """
    加工済みデータ（2次元リスト）をGoogleスプレッドシートの「登録数」シートに書き込みます。
    """
    # 1. 認証設定
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    # サービスアカウントキーファイルのパス
    json_key_file = 'ageless-impulse-488713-m6-03014b3cddad.json'
    
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_file, scope)
        client = gspread.authorize(creds)
        print("✅ Google Sheets API 認証に成功しました。")
    except Exception as e:
        print(f"❌ 認証エラー: {e}")
        return False

    # 2. スプレッドシートを開く
    spreadsheet_id = '1EmVvi7TwjrTc5Mx9wZjqo8G0ZCDrULUqPiD9oeDd97Y'
    sheet_name = '登録数'
    
    try:
        doc = client.open_by_key(spreadsheet_id)
        sheet = doc.worksheet(sheet_name)
        print(f"✅ シート「{sheet_name}」にアクセスしました。")
    except Exception as e:
        print(f"❌ シートアクセスエラー: {e}")
        return False

    # 3. データの書き込み
    try:
        # シートの内容を一度クリアして最新状態にする
        sheet.clear()
        
        # ヘッダーを追加
        header = [['日付', '登録数']]
        full_data = header + data
        
        # A1セルから一括更新
        sheet.update('A1', full_data)
        print(f"✨ {len(data)} 件のデータを「{sheet_name}」シートに書き込みました。")
        return True
    except Exception as e:
        print(f"❌ 書き込みエラー: {e}")
        return False

if __name__ == "__main__":
    # テスト用ダミーデータ
    test_data = [
        ['2024-01-01', 10],
        ['2024-01-02', 15],
        ['2024-01-03', 12],
    ]
    print("Testing upload_to_google_sheets with dummy data...")
    if upload_to_google_sheets(test_data):
        print("✅ Test successful!")
    else:
        print("❌ Test failed.")
