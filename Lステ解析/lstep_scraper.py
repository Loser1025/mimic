import asyncio
import csv
import json
import sys
import re
import os
from playwright.async_api import async_playwright, Playwright

# --- 設定項目 ---
# ログイン画面の正しいURL
LOGIN_URL = "https://manager.linestep.net/account/login"
LSTEP_BASE_URL = "https://manager.linestep.net"

# 各種ファイルのパス
ACCOUNTS_FILE = "/home/loser/projects/-/Lステ解析/アカウント.json"
CSV_FILE = "/home/loser/projects/-/Lステ解析/処理用シート - シート1.csv"

# ログイン情報
CREDENTIALS = {
    "username": "double_juno",
    "password": "evhiBp4B"
}

# 抽出キーワード
KEYWORDS = ["解約", "キャンセル", "クーリングオフ"]

# HTML要素のセレクタ
LOGIN_USERNAME_SELECTOR = "input#input_name"
LOGIN_PASSWORD_SELECTOR = "input#input_password"
LOGIN_BUTTON_SELECTOR = "button.loginButton"

CHAT_CONTAINER_SELECTOR = ".tw-overflow-y-scroll"
LOAD_MORE_BUTTON_SELECTOR = 'button[data-testid="linyBtn"]'
MESSAGE_BLOCK_SELECTOR = "div[data-message-id]"
MESSAGE_CONTENT_SELECTOR = "p.text-content"
DATE_HEADER_SELECTOR = ".tw-bg-n-verypale p"

# --- 補助関数 ---

def load_accounts(file_path):
    """アカウント情報をJSONから読み込む"""
    try:
        if not os.path.exists(file_path):
            print(f"❌ アカウントファイルが見つかりません: {file_path}")
            return {}
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {acc.get('name'): acc.get('id') for acc in data if acc.get('name')}
    except Exception as e:
        print(f"⚠️ アカウントファイル読み込みエラー: {e}")
        return {}

def read_csv(file_path):
    """CSVファイルを読み込む（BOM付きUTF-8対応）"""
    try:
        if not os.path.exists(file_path):
            print(f"❌ CSVファイルが見つかりません: {file_path}")
            return []
        with open(file_path, 'r', encoding='utf-8-sig', newline='') as f:
            return list(csv.reader(f))
    except Exception as e:
        print(f"⚠️ CSV読み込みエラー: {e}")
        return []

def write_csv(file_path, data):
    """CSVファイルを保存する"""
    try:
        with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(data)
        print(f"💾 進捗をCSVに保存しました")
    except Exception as e:
        print(f"❌ CSV書き込みエラー: {e}")

async def load_all_chat_history(page):
    """「続きをロード」ボタンを繰り返しクリックして全履歴を表示させる"""
    print("⏳ 過去ログを遡っています...")
    while True:
        btn = page.locator(LOAD_MORE_BUTTON_SELECTOR).filter(has_text="続きをロード")
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            await asyncio.sleep(2)
        else:
            break
    print("✅ すべての履歴を表示しました")

async def scrape_chat_for_keywords(page):
    """チャット画面からキーワードを探し、最初に見つかった日付を返す"""
    current_date = "日付不明"
    elements = await page.locator(f"{DATE_HEADER_SELECTOR}, {MESSAGE_BLOCK_SELECTOR}").all()
    
    for el in elements:
        text = await el.text_content()
        if "年" in text and "月" in text:
            current_date = text.strip()
            continue
        
        content_el = el.locator(MESSAGE_CONTENT_SELECTOR)
        if await content_el.count() > 0:
            msg_text = await content_el.text_content()
            if any(k in msg_text for k in KEYWORDS):
                return current_date
    return None

async def run(playwright: Playwright):
    """メイン実行ロジック"""
    print("🚀 ブラウザを起動しています...")
    
    # WSL環境でGUIが表示されない原因を特定するためのチェック
    if "DISPLAY" not in os.environ:
        print("⚠️ 警告: DISPLAY環境変数が設定されていません。")

    try:
        # ブラウザを表示モードで起動
        # WSL環境向けに --no-sandbox 引数を追加
        browser = await playwright.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
    except Exception as e:
        print(f"❌ ブラウザの起動に失敗しました: {e}")
        print("Ubuntu側で 'playwright install-deps' を実行したか確認してください。")
        return

    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        viewport={'width': 1280, 'height': 800},
        locale="ja-JP"
    )
    page = await context.new_page()
    
    csv_data = read_csv(CSV_FILE)
    if not csv_data:
        await browser.close()
        return

    try:
        # --- 1. ログイン処理 ---
        print(f"🚀 ログイン画面へ移動中: {LOGIN_URL}")
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        
        await asyncio.sleep(3)
        page_title = await page.title()
        print(f"📄 表示中のページ: {page_title}")
        
        if "Not found" in page_title or "404" in page_title:
            print("❌ ページが見つかりません。")
            await page.screenshot(path="debug_not_found.png")
            return

        # 画面が出るまで待機
        await page.wait_for_selector(LOGIN_USERNAME_SELECTOR, timeout=30000)

        print("⌨️ ログイン情報を入力中...")
        await page.fill(LOGIN_USERNAME_SELECTOR, CREDENTIALS["username"])
        await page.fill(LOGIN_PASSWORD_SELECTOR, CREDENTIALS["password"])
        
        # ログインボタンをクリック
        await page.click(LOGIN_BUTTON_SELECTOR)
        
        # ログイン後の遷移を待機
        print("⏳ ログイン後の遷移を待機しています...")
        await page.wait_for_url("**/account/search", timeout=60000)
        print("🔓 ログイン成功")
        await asyncio.sleep(2)

        # --- 2. CSVの各行をループ処理 ---
        for i, row in enumerate(csv_data):
            if i == 0: continue
            if len(row) < 5 or row[0]: continue
            
            # URL抽出
            url_match = re.search(r'https://manager\.linestep\.net/chat/show/\S+', row[4])
            if not url_match: continue
            
            target_url = url_match.group().strip().rstrip(')>]"\'')
            print(f"\n🔍 処理開始 ({i}/{len(csv_data)-1}): {target_url}")
            
            try:
                response = await page.goto(target_url, wait_until="networkidle")
                
                if response.status == 404:
                    print(f"⚠️ 404エラー。スキップします。")
                    continue

                await page.wait_for_selector(CHAT_CONTAINER_SELECTOR, timeout=20000)
                await load_all_chat_history(page)
                found_date = await scrape_chat_for_keywords(page)
                
                if found_date:
                    csv_data[i][0] = found_date
                    print(f"✨ キーワード発見: {found_date}")
                    write_csv(CSV_FILE, csv_data)
                else:
                    print("🤷 キーワードは見つかりませんでした")
                
            except Exception as e:
                print(f"⚠️ 行 {i+1} でエラー: {e}")
                continue

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        await page.screenshot(path="fatal_error.png")
    finally:
        await browser.close()
        print("🏁 すべての工程が終了しました")

async def main():
    async with async_playwright() as p:
        await run(p)

if __name__ == "__main__":
    asyncio.run(main())