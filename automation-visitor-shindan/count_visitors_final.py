import asyncio
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

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

async def login_and_get_page(p):
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
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return gspread.authorize(creds)

async def run_management_extraction():
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        try:
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
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
            
            # Try multiple selectors for the search button
            search_button = page.get_by_role("button", name="絞込")
            if await search_button.count() == 0:
                # Fallback: search for button containing "絞込"
                search_button = page.locator("button:has-text('絞込')")
            
            await search_button.click()
            await page.wait_for_load_state("networkidle")
            
            export_button = page.get_by_role("button", name="CSV抽出")
            if await export_button.count() == 0:
                export_button = page.locator("button:has-text('CSV抽出')")
                
            await export_button.click()
            async with page.expect_download() as download_info:
                await asyncio.sleep(1) 
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            await upload_raw_data_to_sheet(CSV_TEMP_PATH, SHEET_NAMES["extraction"])
        except Exception as e:
            print(f"Error in run_management_extraction: {e}")
            await page.screenshot(path=r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\error_extraction.png")
            # Print all buttons to help debug
            buttons = await page.locator("button").all_inner_texts()
            print(f"Available buttons: {buttons}")
            raise e
        finally:
            await browser.close()

async def upload_raw_data_to_sheet(csv_path, sheet_name):
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        df = pd.read_csv(csv_path, encoding="shift_jis")
        df = df.fillna("")
        worksheet.clear()
        data = [df.columns.values.tolist()] + df.values.tolist()
        data_str = [[str(cell) for cell in row] for row in data]
        worksheet.update('A1', data_str, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"Error in upload_raw_data_to_sheet: {e}")

async def run_appointment_aggregation():
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        try:
            # Corrected mojibake for "予約電話"
            status_dropdown = page.locator("#status_chu")
            await status_dropdown.select_option(label="予約電話")
            
            today = datetime.now()
            day_after_tomorrow = today + timedelta(days=2)
            await page.locator("#DateLastStart-y").select_option(value=str(today.year))
            await asyncio.sleep(0.7)
            await page.locator("#DateLastStart-m").select_option(index=today.month)
            await asyncio.sleep(0.7)
            await page.locator("#DateLastStart-d").select_option(index=today.day)
            await asyncio.sleep(0.7)
            await page.locator("#DateLastEnd-y").select_option(value=str(day_after_tomorrow.year))
            await asyncio.sleep(0.7)
            await page.locator("#DateLastEnd-m").select_option(index=day_after_tomorrow.month)
            await asyncio.sleep(0.7)
            await page.locator("#DateLastEnd-d").select_option(index=day_after_tomorrow.day)
            
            search_button = page.get_by_role("button", name="絞込")
            if await search_button.count() == 0:
                search_button = page.locator("button:has-text('絞込')")
                
            await search_button.click()
            await page.wait_for_load_state("networkidle")
            
            export_button = page.get_by_role("button", name="CSV抽出")
            if await export_button.count() == 0:
                export_button = page.locator("button:has-text('CSV抽出')")
                
            await export_button.click()
            async with page.expect_download() as download_info:
                await asyncio.sleep(1) 
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            await upload_pivot_to_sheet(CSV_TEMP_PATH, SHEET_NAMES["aggregation"])
        except Exception as e:
            print(f"Error in run_appointment_aggregation: {e}")
            await page.screenshot(path=r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\error_aggregation.png")
            buttons = await page.locator("button").all_inner_texts()
            print(f"Available buttons: {buttons}")
            raise e
        finally:
            await browser.close()

async def upload_pivot_to_sheet(csv_path, sheet_name):
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        
        df = pd.read_csv(csv_path, encoding="shift_jis")
        df = df.fillna("")
        
        today_str = datetime.now().strftime("%Y/%m/%d")
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y/%m/%d")
        
        # Filter for today and tomorrow
        df_filtered = df[df['次回対応日'].isin([today_str, tomorrow_str])]
        
        if df_filtered.empty:
            print("No data found for today or tomorrow.")
            return
            
        # Process the pivot data
        pivot_data = []
        
        # Get unique people (person identified by '本人確認状況' or similar)
        people = df_filtered['本人確認状況'].unique()
        
        for person in people:
            row = [person]
            for day in [today_str, tomorrow_str]:
                for hour in range(9, 22):
                    hour_str = f"{hour:02}:00"
                    count = len(df_filtered[(df_filtered['次回対応日'] == day) & 
                                           (df_filtered['予約時間'] == hour_str)])
                    row.append(count)
                row.append("") # Separator
            pivot_data.append(row)
        
        # Create headers
        headers = ["担当者"]
        for day in [today_str, tomorrow_str]:
            for hour in range(9, 22):
                headers.append(f"{day} {hour:02}:00")
            headers.append("") # Separator
            
        final_data = [headers] + pivot_data
        data_str = [[str(cell) for cell in row] for row in final_data]
        worksheet.append_rows(data_str, value_input_option="USER_ENTERED")
        
    except Exception as e:
        print(f"Error in upload_pivot_to_sheet: {e}")

async def main():
    try:
        await run_management_extraction()
        print("Management extraction completed successfully.")
        await run_appointment_aggregation()
        print("Appointment aggregation completed successfully.")
    except Exception as e:
        print(f"Main process failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
