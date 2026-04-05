import google.generativeai as genai
import os
from dotenv import load_dotenv

# .envファイルのパスを指定して読み込む
env_path = r'C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\.env'
load_dotenv(env_path)

# .envからGOOGLE_API_KEYを取得
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print(f"エラー: {env_path} 内に 'GOOGLE_API_KEY' が見つかりませんでした。")
else:
    genai.configure(api_key=api_key)
    print("--- 利用可能なモデル一覧 ---")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                # この 'm.name' に表示される文字列が .env に書くべき正しいIDです
                print(f"モデル名: {m.name}  (表示名: {m.display_name})")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
