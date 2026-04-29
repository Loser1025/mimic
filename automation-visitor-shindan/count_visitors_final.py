import asyncio
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

# --- 設定定数 ---
SERVICE_ACCOUNT_FILE = r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json"
SHEET_ID = "1EmVvi7TwjrTc5Mx9wZjqo8G0ZCDrULUqPiD9oeDd97Y"
SHEET_NAMES = {
    "extraction": "管理画面抽出",
    "aggregation": "約束集計表"
}

LOGIN_URL = "https://shindan-kh.com/management/index.php"
TARGET_URL = "https://shindan-kh.com/management/visitor01.php"
USER_ID = "hirota.t"
USER_PASS = "hirota1002"
CSV_TEMP_PATH = r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\temp_export.csv"

# --- 共通関数 ---
async def login_and_get_page(p):
    """ログインしてターゲットページに遷移する"""
    browser = await p.chromium.launch(headless=False) 
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(LOGIN_URL)
    await page.get_by_role("textbox", name="ID").fill(USER_ID)
    await page.get_by_role("textbox", name="パスワード").fill(USER_PASS)
    await page.get_by_role("button", name="ログイン").click()
    await page.wait_for_load_state("networkidle")
    await page.goto(TARGET_URL)
    await page.wait_for_load_state("networkidle")
    return browser, page

def get_gspread_client():
    """Google Sheets APIクライアントを認証して返す"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return gspread.authorize(creds)

# --- メイン処理1: 管理画面抽出 ---
async def run_management_extraction():
    """本日〜明日のデータを抽出し、シートに上書き保存する"""
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        try:
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            
            # 日付設定 (開始: 今日, 終了: 明日)
            await page.locator("#DateLastStart-y").select_option(value=str(today.year))
            await asyncio.sleep(0.7)
            await page.locator("#DateLastStart-m").select_option(index=today.month)
            await asyncio.sleep(0.7)
            await page.locator("#DateLastStart-d").select_option(index=today.day)
            await asyncio.sleep(0.7)
            await page.locator("#DateLastEnd-y").select_option(value=str(tomorrow.year))
            await asyncio.sleep(0.7)
            await page.locator("#DateLastEnd-m").select_option(index=tomorrow.month)
            await asyncio.sleep(0.7)
            await page.locator("#DateLastEnd-d").select_option(index=tomorrow.day)
            
            # 絞込実行
            search_button = page.get_by_role("button", name="絞込")
            if await search_button.count() == 0:
                search_button = page.locator("button:has-text('絞込')")
            await search_button.click()
            await page.wait_for_load_state("networkidle")
            
            # CSV抽出
            export_button = page.get_by_role("button", name="CSV抽出")
            if await export_button.count() == 0:
                export_button = page.locator("button:has-text('CSV抽出')")
            await export_button.click()
            
            async with page.expect_download() as download_info:
                await asyncio.sleep(1) 
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            
            # スプレッドシートへアップロード
            await upload_raw_data_to_sheet(CSV_TEMP_PATH, SHEET_NAMES["extraction"])
            print("Management extraction completed successfully.")
            
        except Exception as e:
            print(f"Error in run_management_extraction: {e}")
            await page.screenshot(path=r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\error_extraction.png")
            buttons = await page.locator("button").all_inner_texts()
            print(f"Available buttons: {buttons}")
            raise e
        finally:
            await browser.close()

async def upload_raw_data_to_sheet(csv_path, sheet_name):
    """CSVデータを読み込み、シートをクリアして上書きする"""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        
        df = pd.read_csv(csv_path, encoding="shift_jis")
        df = df.fillna("")
        
        worksheet.clear()
        # ヘッダーを含めてデータをリスト化
        data = [df.columns.values.tolist()] + df.values.tolist()
        data_str = [[str(cell) for cell in row] for row in data]
        
        worksheet.update(range_name='A1', values=data_str, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"Error in upload_raw_data_to_sheet: {e}")

# --- メイン処理2: 約束集計 ---
async def run_appointment_aggregation():
    """予約電話データを全件抽出し、本日・明日の分を集計してシートに追記する"""
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        try:
            # ステータス絞り込み (日付は絞り込まない)
            status_dropdown = page.locator("#status_chu")
            await status_dropdown.select_option(label="予約電話")
            
            # 絞込実行
            search_button = page.get_by_role("button", name="絞込")
            if await search_button.count() == 0:
                search_button = page.locator("button:has-text('絞込')")
            await search_button.click()
            await page.wait_for_load_state("networkidle")
            
            # CSV抽出
            export_button = page.get_by_role("button", name="CSV抽出")
            if await export_button.count() == 0:
                export_button = page.locator("button:has-text('CSV抽出')")
            await export_button.click()
            
            async with page.expect_download() as download_info:
                await asyncio.sleep(1) 
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            
            # ピボット集計してアップロード
            await upload_pivot_to_sheet(CSV_TEMP_PATH, SHEET_NAMES["aggregation"])
            print("Appointment aggregation completed successfully.")
            
        except Exception as e:
            print(f"Error in run_appointment_aggregation: {e}")
            await page.screenshot(path=r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\error_aggregation.png")
            buttons = await page.locator("button").all_inner_texts()
            print(f"Available buttons: {buttons}")
            raise e
        finally:
            await browser.close()

async def upload_pivot_to_sheet(csv_path, sheet_name):
    """CSVから本日・明日のデータを抽出し、時間別集計表を作成して追記する"""
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        
        df = pd.read_csv(csv_path, encoding="shift_jis")
        df = df.fillna("")
        
        # 日付形式をハイフン区切りに統一
        today_str = datetime.now().strftime("%Y-%m-%d")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        # 「次回対応日」を日付型に変換し、日付部分と時間部分を抽出する
        # 形式例: "2026-05-01 19:00:00" -> date="2026-05-01", hour="19:00"
        df['次回対応日_dt'] = pd.to_datetime(df['次回対応日'])
        df['次回対応日_date'] = df['次回対応日_dt'].dt.strftime('%Y-%m-%d')
        df['次回対応日_hour'] = df['次回対応日_dt'].dt.strftime('%H:00')
        
        # 本日と明日のデータのみを抽出
        df_filtered = df[df['次回対応日_date'].isin([today_str, tomorrow_str])]
        
        if df_filtered.empty:
            print("No data found for today or tomorrow.")
            return
            
        # ピボット集計
        pivot_data = []
        people = df_filtered['本人確認状況'].unique()
        
        for person in people:
            row = [person]
            for day in [today_str, tomorrow_str]:
                for hour in range(9, 22):
                    hour_str = f"{hour:02}:00"
                    # 日付と時間が一致する件数をカウント
                    count = len(df_filtered[(df_filtered['次回対応日_date'] == day) & 
                                           (df_filtered['次回対応日_hour'] == hour_str)])
                    row.append(count)
                row.append("") # 区切り用空白列
            pivot_data.append(row)
        
        # ヘッダー作成
        headers = ["担当者"]
        for day in [today_str, tomorrow_str]:
            for hour in range(9, 22):
                headers.append(f"{day} {hour:02}:00")
            headers.append("") # 区切り用空白列
            
        final_data = [headers] + pivot_data
        data_str = [[str(cell) for cell in row] for row in final_data]
        
        worksheet.append_rows(data_str, value_input_option="USER_ENTERED")
        
    except Exception as e:
        print(f"Error in upload_pivot_to_sheet: {e}")

async def main():
    """メイン実行フロー"""
    try:
        # 1. 管理画面抽出 (当日〜翌日 / 上書き)
        await run_management_extraction()
        # 2. 約束集計 (予約電話全件抽出し本日・翌日分を集計 / 追記)
        await run_appointment_aggregation()
    except Exception as e:
        print(f"Main process failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
