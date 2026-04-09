import asyncio
import os
import pandas as pd
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

# ================= 設定変更 =================
# 自身のディレクトリを取得
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Googleスプレッドシート設定
SS_ID = "1EmVvi7TwjrTc5Mx9wZjqo8G0ZCDrULUqPiD9oeDd97Y"
SHEET_NAME = "約束集計表"
# 認証ファイルのパス
CREDS_PATH = os.path.join(BASE_DIR, "ageless-impulse-488713-m6-03014b3cddad.json")

# ログイン情報
LOGIN_ID = "hirota.t"
LOGIN_PW = "hirota1002"
TARGET_URL = "https://shindan-kh.com/management/visitor01.php"
LOGIN_URL = "https://shindan-kh.com/management/index.php"
HOME_URL = "https://shindan-kh.com/"

# CSV一時保存パス
CSV_TEMP_PATH = os.path.join(BASE_DIR, "temp_visitor_export.csv")

# ===========================================

async def run_automation():
    async with async_playwright() as p:
        # ブラウザ起動（ヘッドレスモード = 画面表示なし）
        print("ブラウザを起動しています（ヘッドレスモード）...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # ボット検知回避のため、まずトップページへ
        print("サイトにアクセスします...")
        await page.goto(HOME_URL, wait_until="domcontentloaded")
        
        print("ログインページへ移動します...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        print("ログイン処理を開始します...")
        await page.get_by_role("textbox", name="ID").fill(LOGIN_ID)
        await page.get_by_role("textbox", name="パスワード").fill(LOGIN_PW)
        await page.get_by_role("button", name="ログイン").click()

        # ログイン後のリダイレクト完了待ち
        print("ログイン完了待ち...")
        try:
            await page.wait_for_url("**/management/**", timeout=15000)
        except:
            print("URLの変化を検知できませんでしたが、続行します。")
        
        await asyncio.sleep(3)

        # --- 相談一覧ページへ移動（リトライ機能付き） ---
        print("相談一覧ページへ移動します...")
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                break 
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 3
                    print(f"移動中にエラーが発生しました: {e}、{wait_time}秒後に再試行します... ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise e

        # --- 絞り込み条件の設定 ---
        print("本人確認状況(中分類)を『予約電話』に設定します...")
        await page.locator("select").filter(has=page.locator("option:has-text('予約電話')")).select_option(label="予約電話")

        print("条件を絞り込みます...")
        await page.get_by_role("button", name="絞込").click()
        await page.wait_for_load_state("networkidle")

        # 訪問者数の取得
        try:
            count_text = await page.locator(".total-count").inner_text()
            print(f"【確認】本日の訪問者数: {count_text}")
        except:
            print("訪問者数のテキスト取得に失敗しましたが、処理を続行します。")

        print("CSVを抽出しています...")
        try:
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="CSV抽出").click()
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            print(f"CSVを保存しました: {CSV_TEMP_PATH}")
        except Exception as e:
            print(f"CSV抽出中にエラーが発生しました: {e}")
            await browser.close()
            return

        await browser.close()

        # --- Googleスプレッドシートへのアップロード ---
        print("スプレッドシートにデータをアップロードしています...")
        try:
            # CSV読み込み (shift-JISを想定)
            df = pd.read_csv(CSV_TEMP_PATH, encoding="shift_jis")
            
            # NaNを空文字に変換
            df = df.fillna("")
            
            # ヘッダーを含めてリスト化
            data_to_upload = [df.columns.values.tolist()] + df.values.tolist()
            
            # Google Sheets 認証
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_file(CREDS_PATH, scopes=scope)
            gc = gspread.authorize(creds)
            
            # シートを開く
            sh = gc.open_by_key(SS_ID)
            worksheet = sh.worksheet(SHEET_NAME)
            
            # 既存データをクリアして貼り付け
            worksheet.clear()
            worksheet.update(values=data_to_upload, range_name='A1')
            
            print(f"成功: {len(df)}件のデータを「{SHEET_NAME}」シートに書き込みました。")
        except Exception as e:
            print(f"スプレッドシート更新中にエラーが発生しました: {e}")

if __name__ == "__main__":
    asyncio.run(run_automation())