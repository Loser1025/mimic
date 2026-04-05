import subprocess
import sys

def main():
    print("="*50)
    print(" Playwright 操作レコーダー起動ツール")
    print("="*50)
    print("このツールは、ブラウザでの操作を自動的にPythonコードに変換します。")
    print("終了するには、ブラウザまたはInspectorウィンドウを閉じてください。")
    print("-" * 50)
    
    url = input("録画を開始したいURLを入力してください (例: https://shindan-kh.com/management/index.php): ").strip()
    
    if not url:
        print("URLが入力されなかったため、デフォルトのページで起動します。")
        url = "https://shindan-kh.com/management/index.php"

    print(f"\nレコーダーを起動しています... \nターゲットURL: {url}")
    print("-" * 50)
    
    try:
        # 現在のPython実行環境（仮想環境含む）を使用して playwright codegen を実行
        subprocess.run([sys.executable, "-m", "playwright", "codegen", url], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\nエラーが発生しました: {e}")
    except KeyboardInterrupt:
        print("\nユーザーによって中断されました。")
    
    print("\nレコーダーを終了しました。")

if __name__ == "__main__":
    main()
