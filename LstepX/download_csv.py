import os
from playwright.sync_api import Playwright, sync_playwright, expect

# 設定
USER_ID = "kogawa_flka"
PASSWORD = "kogawa0930"
DOWNLOAD_DIR = r"C:\Users\Loser\Desktop\-\-\LstepX"

def run(playwright: Playwright) -> None:
    # ブラウザを起動 (CAPTCHA操作のため headless=False)
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    print("ログインページに移動しています...")
    page.goto("https://manager.linestep.net/account/login")

    # ユーザーID入力
    page.get_by_role("textbox", name="ユーザーID").fill(USER_ID)
    # パスワード入力
    page.get_by_role("textbox", name="パスワード").fill(PASSWORD)

    print("CAPTCHAのチェックボックスをクリックします。追加認証が必要な場合は手動で操作してください。")
    try:
        # 録画に基づいたCAPTCHAチェックボックスのクリック
        # iframeの名前は動的に変わる可能性があるため、部分一致などで対応することを推奨しますが、一旦録画通りに実装します
        page.locator("iframe[name*='a-']").first.content_frame.get_by_role("checkbox", name="私はロボットではありません").click(timeout=5000)
    except Exception as e:
        print(f"CAPTCHAの自動クリックに失敗しました（または既に完了しています）: {e}")

    # ログインボタンクリック
    page.get_by_role("button", name="ログイン").click()

    # ログイン完了まで待機 (ダッシュボードの要素が表示されるまで)
    # ここで手動操作の時間を確保するため、タイムアウトを長めに設定して待機します
    print("ログイン完了を待機しています...")
    page.wait_for_url("**/dashboard**", timeout=60000) 

    print("クロス分析ページへ移動します...")
    # クロス分析へのリンクをクリックしてボードへ移動
    page.goto("https://manager.linestep.net/line/board")

    # 「反響数？」リンクをクリック
    page.get_by_role("link", name="反響数？").click()

    # 日付選択 (終点) を操作
    page.get_by_role("textbox", name="日付選択(終点)").click()
    # 録画では5番目の「5」をクリックしていたため、それに合わせます
    page.get_by_text("5").nth(5).click()

    # 分析登録ボタンをクリック
    page.get_by_text("分析登録", exact=True).click()

    # 新しいウィンドウで分析を表示
    print("分析結果を新しいウィンドウで開きます...")
    with page.expect_popup() as page1_info:
        page.get_by_role("link", name="分析を表示する").click()
    page1 = page1_info.value

    # 再計算ボタンをクリック
    page1.get_by_role("button", name=" 再計算").click()

    # CSVエクスポートのダウンロード
    print("CSVファイルをダウンロードしています...")
    with page1.expect_download() as download_info:
        page1.get_by_role("link", name="CSVエクスポート").click()
    
    download = download_info.value
    
    # 保存先のパスを決定 (ファイル名を保持)
    save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
    download.save_as(save_path)
    
    print(f"ファイルを保存しました: {save_path}")

    # 終了処理
    context.close()
    browser.close()

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
