code = r'''
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
    "extraction": "驍ゑｽ｡騾・・蛻､鬮ｱ・｢隰夲ｽｽ陷・ｽｺ",
    "aggregation": "驍上・謫夐ｫｮ繝ｻ・ｨ驛・ｽ｡・ｨ"
}

LOGIN_URL = "https://shindan-kh.com/management/index.php"
TARGET_URL = "https://shindan-kh.com/management/visitor01.php"
USER_ID = "hirota.t"
USER_PASS = "hirota1002"
CSV_TEMP_PATH = r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\temp_export.csv"

async def login_and_get_page(p):
    browser = await p.chromium.launch(headless=True) 
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto(LOGIN_URL)
    await page.get_by_role("textbox", name="ID").fill(USER_ID)
    await page.get_by_role("textbox", name="\u30d1\u30b9\u30ef\u30fc\u30c9").fill(USER_PASS)
    await page.get_by_role("button", name="\u30ed\u30b4\u30a4\u30b3\u30f3").click()
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
            await page.get_by_role("button", name="\u691c\u7d22").click()
            await page.wait_for_load_state("networkidle")
            await page.get_by_role("button", name="CSV\u63d8\u51fa").click()
            async with page.expect_download() as download_info:
                await asyncio.sleep(1) 
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            await upload_raw_data_to_sheet(CSV_TEMP_PATH, SHEET_NAMES["extraction"])
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
        print(f"Error: {e}")

async def run_appointment_aggregation():
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        try:
            await page.locator("#status_chu").select_option(label="\u4e88\u7d0a\u9B54\u8a71")
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
            await page.get_by_role("button", name="\u691c\u7d22").click()
            await page.wait_for_load_state("networkidle")
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="CSV\u63d8\u51fa").click()
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            await upload_pivot_to_sheet(SHEET_NAMES["aggregation"])
        finally:
            await browser.close()

async def upload_pivot_to_sheet(sheet_name):
    try:
        df = pd.read_csv(CSV_TEMP_PATH, encoding="shift_jis")
        df = df.fillna("")
        col_date = '隹ｺ・｡陜玲ｧｫ・ｯ・ｾ陟｢諛亥ｾ・ 
        col_person = '隴幢ｽｬ闔・ｺ驕抵ｽｺ髫ｱ蜥ｲ諞ｾ雎輔・'
        df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
        today_date = datetime.now().date()
        tomorrow_date = today_date + timedelta(days=1)
        df_target = df[df[col_date].dt.date.isin([today_date, tomorrow_date])].copy()
        if df_target.empty:
            return
        def create_pivot(target_date):
            df_date = df_target[df_target[col_date].dt.date == target_date].copy()
            start_time = datetime.combine(target_date, datetime.min.time()).replace(hour=9)
            end_time = datetime.combine(target_date, datetime.min.time()).replace(hour=21)
            all_hours = pd.date_range(start=start_time, end=end_time, freq='h')
            if df_date.empty:
                return pd.DataFrame(0, index=df_target[col_person].unique(), columns=all_hours)
            df_date['hour'] = df_date[col_date].dt.floor('h')
            pivot = df_date.pivot_table(index=col_person, columns='hour', values=col_date, aggfunc='count', fill_value=0)
            return pivot.reindex(columns=all_hours, fill_value=0)
        pivot_today = create_pivot(today_date)
        pivot_tomorrow = create_pivot(tomorrow_date)
        all_indices = pivot_today.index.union(pivot_tomorrow.index)
        pivot_today = pivot_today.reindex(all_indices, fill_value=0)
        pivot_tomorrow = pivot_tomorrow.reindex(all_indices, fill_value=0)
        today_hours = pd.date_range(start=datetime.combine(today_date, datetime.min.time()).replace(hour=9), 
                                    end=datetime.combine(today_date, datetime.min.time()).replace(hour=21), freq='h')
        tomorrow_hours = pd.date_range(start=datetime.combine(tomorrow_date, datetime.min.time()).replace(hour=9), 
                                       end=datetime.combine(tomorrow_date, datetime.min.time()).replace(hour=21), freq='h')
        headers = [col_person] + [h.strftime('%Y/%m/%d %H:%M') for h in today_hours] + [''] + [h.strftime('%Y/%m/%d %H:%M') for h in tomorrow_hours]
        data_to_append = []
        for idx in all_indices:
            row = [idx] + pivot_today.loc[idx].tolist() + [''] + pivot_tomorrow.loc[idx].tolist()
            data_to_append.append(row)
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        worksheet.append_rows([headers] + data_to_append, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    try:
        await run_management_extraction()
        await run_appointment_aggregation()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
'''
with open(r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\count_visitors_final.py", "w", encoding="utf-8") as f:
    f.write(code)