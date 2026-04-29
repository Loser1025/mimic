import asyncio
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 險ｭ螳壽ュ蝣ｱ
# ==========================================
# Google繧ｵ繝ｼ繝薙せ繧｢繧ｫ繧ｦ繝ｳ繝・SON繝代せ
SERVICE_ACCOUNT_FILE = r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json"
SHEET_ID = "1EmVvi7TwjrTc5Mx9wZjqo8G0ZCDrULUqPiD9oeDd97Y"
SHEET_NAMES = {
    "extraction": "驍ゑｽ｡騾・・蛻､鬮ｱ・｢隰夲ｽｽ陷・ｽｺ",
    "aggregation": "驍上・謫夐ｫｮ繝ｻ・ｨ驛・ｽ｡・ｨ"
}

# 繝ｭ繧ｰ繧､繝ｳ諠・ｱ
LOGIN_URL = "https://shindan-kh.com/management/index.php"
TARGET_URL = "https://shindan-kh.com/management/visitor01.php"
USER_ID = "hirota.t"
USER_PASS = "hirota1002"

# 荳譎・SV菫晏ｭ倥ヱ繧ｹ
CSV_TEMP_PATH = r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\temp_export.csv"

# ==========================================
# 蜈ｱ騾夐未謨ｰ
# ==========================================
async def login_and_get_page(p):
    """繝ｭ繧ｰ繧､繝ｳ縺励※繧ｿ繝ｼ繧ｲ繝・ヨ繝壹・繧ｸ縺ｫ驕ｷ遘ｻ縺用age繧ｪ繝悶ず繧ｧ繧ｯ繝医ｒ霑斐☆"""
    browser = await p.chromium.launch(headless=True) 
    context = await browser.new_context()
    page = await context.new_page()

    print("繝ｭ繧ｰ繧､繝ｳ繝壹・繧ｸ縺ｫ繧｢繧ｯ繧ｻ繧ｹ荳ｭ...")
    await page.goto(LOGIN_URL)

    print("繝ｭ繧ｰ繧､繝ｳ諠・ｱ繧貞・蜉帑ｸｭ...")
    await page.get_by_role("textbox", name="ID").fill(USER_ID)
    await page.get_by_role("textbox", name="繝代せ繝ｯ繝ｼ繝・).fill(USER_PASS)
    await page.get_by_role("button", name="繝ｭ繧ｰ繧､繝ｳ").click()
    await page.wait_for_load_state("networkidle")

    print("繧ｿ繝ｼ繧ｲ繝・ヨ繝壹・繧ｸ縺ｸ驕ｷ遘ｻ荳ｭ...")
    await page.goto(TARGET_URL)
    await page.wait_for_load_state("networkidle")

    return browser, page

def get_gspread_client():
    """Google Sheets API繧ｯ繝ｩ繧､繧｢繝ｳ繝医ｒ蛻晄悄蛹・""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return gspread.authorize(creds)

# ==========================================
# 蜃ｦ逅・: 逕溘ョ繝ｼ繧ｿ縺ｮ謚ｽ蜃ｺ
# ==========================================
async def run_management_extraction():
    """蜃ｦ逅・: 譛ｬ譌･縺ｮ繝・・繧ｿ繧呈歓蜃ｺ縺励※繧ｹ繝励Ξ繝・ラ繧ｷ繝ｼ繝医↓菫晏ｭ・""
    print("\n--- [蜃ｦ逅・] 逕溘ョ繝ｼ繧ｿ謚ｽ蜃ｺ縺ｮ髢句ｧ九ｒ蜃ｦ逅・＠縺ｾ縺・---")
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        
        try:
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            print(f"譌･莉倥ｒ險ｭ螳壹＠縺ｦ縺・∪縺・. ({today.strftime('%Y-%m-%d')} 縲・{tomorrow.strftime('%Y-%m-%d')})")
            
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

            print("譚｡莉ｶ繧呈､懃ｴ｢荳ｭ...")
            await page.get_by_role("button", name="讀懃ｴ｢").click()
            await page.wait_for_load_state("networkidle")

            print("CSV繧偵ム繧ｦ繝ｳ繝ｭ繝ｼ繝峨＠縺ｦ縺・∪縺・..")
            await page.get_by_role("button", name="CSV謚ｽ蜃ｺ").click()
            async with page.expect_download() as download_info:
                await asyncio.sleep(1) 
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            print(f"CSV繧剃ｿ晏ｭ倥＠縺ｾ縺励◆: {CSV_TEMP_PATH}")
            
            await upload_raw_data_to_sheet(CSV_TEMP_PATH, SHEET_NAMES["extraction"])

        finally:
            await browser.close()

async def upload_raw_data_to_sheet(csv_path, sheet_name):
    """CSV繝・・繧ｿ繧偵◎縺ｮ縺ｾ縺ｾ繧ｹ繝励Ξ繝・ラ繧ｷ繝ｼ繝医↓菫晏ｭ倥☆繧・""
    print(f"繧ｹ繝励Ξ繝・ラ繧ｷ繝ｼ繝・{sheet_name} 縺ｫ繝・・繧ｿ繧呈嶌縺崎ｾｼ繧薙〒縺・∪縺・..")
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
        
        print(f"謌仙粥: {len(df)} 莉ｶ縺ｮ繝・・繧ｿ繧・{sheet_name} 縺ｫ譖ｸ縺崎ｾｼ縺ｿ縺ｾ縺励◆縲・)
    except Exception as e:
        print(f"繧ｨ繝ｩ繝ｼ逋ｺ逕・ {e}")

# ==========================================
# 蜃ｦ逅・: 莠育ｴ・憾豕√・髮・ｨ・
# ==========================================
async def run_appointment_aggregation():
    """蜃ｦ逅・: 莠育ｴ・崕隧ｱ謚ｽ蜃ｺ -> 髮・ｨ郁｡ｨ縺ｸ譖ｸ縺崎ｾｼ縺ｿ (蠖捺律繝ｻ鄙梧律縺ｮ2譌･蛻・"""
    print("\n--- [蜃ｦ逅・] 莠育ｴ・寔險郁｡ｨ縺ｮ髢句ｧ九ｒ蜃ｦ逅・＠縺ｾ縺・---")
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        
        try:
            print("繧ｹ繝・・繧ｿ繧ｹ荳ｭ蛻・｡槭ｒ縲惹ｺ育ｴ・崕隧ｱ縲上↓險ｭ螳壹＠縺ｦ縺・∪縺・..")
            await page.locator("#status_chu").select_option(label="莠育ｴ・崕隧ｱ")

            # --- 謚ｽ蜃ｺ遽・峇繧堤ｿ梧律縺ｾ縺ｧ諡｡蠑ｵ ---
            today = datetime.now()
            day_after_tomorrow = today + timedelta(days=2)
            print(f"謚ｽ蜃ｺ遽・峇繧定ｨｭ螳壹＠縺ｦ縺・∪縺・. ({today.strftime('%Y-%m-%d')} 縲・{day_after_tomorrow.strftime('%Y-%m-%d')})")
            
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

            print("譚｡莉ｶ繧呈､懃ｴ｢荳ｭ...")
            await page.get_by_role("button", name="讀懃ｴ｢").click()
            await page.wait_for_load_state("networkidle")

            print("CSV繧偵ム繧ｦ繝ｳ繝ｭ繝ｼ繝峨＠縺ｦ縺・∪縺・..")
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="CSV謚ｽ蜃ｺ").click()
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            print(f"CSV繧剃ｿ晏ｭ倥＠縺ｾ縺励◆: {CSV_TEMP_PATH}")

            await upload_pivot_to_sheet(SHEET_NAMES["aggregation"])

        finally:
            await browser.close()

async def upload_pivot_to_sheet(sheet_name):
    """CSV繧偵ヴ繝懊ャ繝磯寔險医＠縲∝ｽ捺律蛻・→鄙梧律蛻・ｒ1蛻礼ｩｺ縺代※菫晏ｭ倥☆繧・""
    print(f"繧ｹ繝励Ξ繝・ラ繧ｷ繝ｼ繝・{sheet_name} 縺ｫ髮・ｨ医ョ繝ｼ繧ｿ繧呈嶌縺崎ｾｼ繧薙〒縺・∪縺・..")
    try:
        df = pd.read_csv(CSV_TEMP_PATH, encoding="shift_jis")
        df = df.fillna("")

        # 蛻怜錐縺ｮ譁・ｭ怜喧縺大ｯｾ遲悶→縺励※縲∝・縺ｮ繧ｳ繝ｼ繝峨〒菴ｿ逕ｨ縺輔ｌ縺ｦ縺・◆蜷咲ｧｰ繧堤ｶｭ謖・
        col_date = '隹ｺ・｡陜玲ｧｫ・ｯ・ｾ陟｢諛亥ｾ・ 
        col_person = '隴幢ｽｬ闔・ｺ驕抵ｽｺ髫ｱ蜥ｲ諞ｾ雎輔・'

        df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
        
        today_date = datetime.now().date()
        tomorrow_date = today_date + timedelta(days=1)
        
        # 蠖捺律繝ｻ鄙梧律縺ｮ繝・・繧ｿ縺ｮ縺ｿ繧貞ｯｾ雎｡縺ｫ縺吶ｋ
        df_target = df[df[col_date].dt.date.isin([today_date, tomorrow_date])].copy()
        
        if df_target.empty:
            print("蟇ｾ雎｡縺ｨ縺ｪ繧九ョ繝ｼ繧ｿ縺瑚ｦ九▽縺九ｊ縺ｾ縺帙ｓ縺ｧ縺励◆縲ょ・逅・ｒ繧ｹ繧ｭ繝・・縺励∪縺吶・)
            return

        def create_pivot(target_date):
            df_date = df_target[df_target[col_date].dt.date == target_date].copy()
            
            # 譎る俣譫(9:00-21:00)繧剃ｽ懈・
            start_time = datetime.combine(target_date, datetime.min.time()).replace(hour=9)
            end_time = datetime.combine(target_date, datetime.min.time()).replace(hour=21)
            all_hours = pd.date_range(start=start_time, end=end_time, freq='h')
            
            if df_date.empty:
                # 繝・・繧ｿ縺後↑縺・ｴ蜷医・0縺ｧ蝓九ａ縺溽ｩｺ縺ｮ繝斐・繝・ヨ繧定ｿ斐☆
                return pd.DataFrame(0, index=df_target[col_person].unique(), columns=all_hours)

            df_date['hour'] = df_date[col_date].dt.floor('h')
            pivot = df_date.pivot_table(
                index=col_person, 
                columns='hour', 
                values=col_date, 
                aggfunc='count', 
                fill_value=0
            )
            return pivot.reindex(columns=all_hours, fill_value=0)

        # 蠖捺律蛻・→鄙梧律蛻・ｒ縺昴ｌ縺槭ｌ髮・ｨ・
        pivot_today = create_pivot(today_date)
        pivot_tomorrow = create_pivot(tomorrow_date)
        
        # 蜈ｨ諡・ｽ楢・ｒ邯ｲ鄒・＠縺溷・騾壹う繝ｳ繝・ャ繧ｯ繧ｹ繧剃ｽ懈・
        all_indices = pivot_today.index.union(pivot_tomorrow.index)
        pivot_today = pivot_today.reindex(all_indices, fill_value=0)
        pivot_tomorrow = pivot_tomorrow.reindex(all_indices, fill_value=0)
        
        # 繝倥ャ繝繝ｼ縺ｮ菴懈・: [諡・ｽ楢・ + [蠖捺律蛻・凾髢転 + [遨ｺ蛻余 + [鄙梧律蛻・凾髢転
        today_hours = pd.date_range(start=datetime.combine(today_date, datetime.min.time()).replace(hour=9), 
                                    end=datetime.combine(today_date, datetime.min.time()).replace(hour=21), freq='h')
        tomorrow_hours = pd.date_range(start=datetime.combine(tomorrow_date, datetime.min.time()).replace(hour=9), 
                                       end=datetime.combine(tomorrow_date, datetime.min.time()).replace(hour=21), freq='h')
        
        headers = [col_person] + [h.strftime('%Y/%m/%d %H:%M') for h in today_hours] + [''] + [h.strftime('%Y/%m/%d %H:%M') for h in tomorrow_hours]
        
        # 繝・・繧ｿ陦後・菴懈・
        data_to_append = []
        for idx in all_indices:
            row = [idx] + pivot_today.loc[idx].tolist() + [''] + pivot_tomorrow.loc[idx].tolist()
            data_to_append.append(row)
        
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        
        # 繧ｹ繝励Ξ繝・ラ繧ｷ繝ｼ繝医・譛ｫ蟆ｾ縺ｫ霑ｽ險・
        worksheet.append_rows([headers] + data_to_append, value_input_option="USER_ENTERED")
        
        print(f"謌仙粥: 蠖捺律蛻・→鄙梧律蛻・・髮・ｨ医ｒ {sheet_name} 縺ｫ譖ｸ縺崎ｾｼ縺ｿ縺ｾ縺励◆縲・)
    except Exception as e:
        print(f"繧ｨ繝ｩ繝ｼ逋ｺ逕・ {e}")

# ==========================================
# 繝｡繧､繝ｳ螳溯｡碁未謨ｰ
# ==========================================
async def main():
    try:
        await run_management_extraction()
        await run_appointment_aggregation()
        print("\n==========================================")
        print("縺吶∋縺ｦ縺ｮ蜃ｦ逅・′豁｣蟶ｸ縺ｫ螳御ｺ・＠縺ｾ縺励◆縲・)
        print("==========================================")
    except Exception as e:
        print(f"\n莠域悄縺帙〓繧ｨ繝ｩ繝ｼ縺檎匱逕溘＠縺ｾ縺励◆: {e}")

if __name__ == "__main__":
    asyncio.run(main())