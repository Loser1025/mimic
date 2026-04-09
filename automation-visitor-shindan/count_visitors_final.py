import asyncio
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 設定情報
# ==========================================
# Googleスプレッドシート設定
SERVICE_ACCOUNT_FILE = r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\ageless-impulse-488713-m6-03014b3cddad.json"
SHEET_ID = "1EmVvi7TwjrTc5Mx9wZjqo8G0ZCDrULUqPiD9oeDd97Y"
SHEET_NAMES = {
    "extraction": "管理画面抽出",
    "aggregation": "約束集計表"
}

# ログイン情報
LOGIN_URL = "https://shindan-kh.com/management/index.php"
TARGET_URL = "https://shindan-kh.com/management/visitor01.php"
USER_ID = "hirota.t"
USER_PASS = "hirota1002"

# 一時CSV保存パス
CSV_TEMP_PATH = r"C:\Users\Loser\Desktop\-\-\automation-visitor-shindan\temp_export.csv"

# ==========================================
# 共通関数
# ==========================================
async def login_and_get_page(p):
    """ログインしてターゲットページまで移動したpageオブジェクトを返す"""
    browser = await p.chromium.launch(headless=True) # ヘッドレスモードで実行
    context = await browser.new_context()
    page = await context.new_page()

    print("ログインページにアクセス中...")
    await page.goto(LOGIN_URL)

    print("ログイン情報を入力中...")
    await page.get_by_role("textbox", name="ID").fill(USER_ID)
    await page.get_by_role("textbox", name="パスワード").fill(USER_PASS)
    await page.get_by_role("button", name="ログイン").click()
    await page.wait_for_load_state("networkidle")

    print("ターゲットページへ移動中...")
    await page.goto(TARGET_URL)
    await page.wait_for_load_state("networkidle")

    return browser, page

def get_gspread_client():
    """Google Sheets APIクライアントを取得"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
    return gspread.authorize(creds)

# ==========================================
# 処理1: 管理画面抽出
# ==========================================
async def run_management_extraction():
    """処理1: 指定期間の全データを抽出してスプレッドシートへ上書き"""
    print("\n--- [処理1] 管理画面抽出の実行を開始します ---")
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        
        try:
            # --- 日付設定 (本日の0:00 〜 明日の0:00) ---
            today = datetime.now()
            tomorrow = today + timedelta(days=1)
            print(f"日付を設定しています... ({today.strftime('%Y-%m-%d')} 〜 {tomorrow.strftime('%Y-%m-%d')})")
            
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

            print("条件を絞り込みます...")
            await page.get_by_role("button", name="絞込").click()
            await page.wait_for_load_state("networkidle")

            print("CSVをダウンロードしています...")
            # CSV抽出ボタンをクリック
            await page.get_by_role("button", name="CSV抽出").click()
            # ダウンロード完了まで待機
            async with page.expect_download() as download_info:
                await asyncio.sleep(1) 
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            print(f"CSVを保存しました: {CSV_TEMP_PATH}")

            # スプレッドシートへアップロード
            await upload_raw_data_to_sheet(CSV_TEMP_PATH, SHEET_NAMES["extraction"])

        finally:
            await browser.close()

async def upload_raw_data_to_sheet(csv_path, sheet_name):
    """CSVデータをそのままスプレッドシートに上書き保存する"""
    print(f"スプレッドシート「{sheet_name}」にデータを書き込んでいます...")
    try:
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)

        df = pd.read_csv(csv_path, encoding="shift_jis")
        df = df.fillna("")

        # 全データをクリアして書き込み
        worksheet.clear()
        # ヘッダーとデータをリスト形式に変換
        data = [df.columns.values.tolist()] + df.values.tolist()
        # 文字列に変換して書き込み
        data_str = [[str(cell) for cell in row] for row in data]
        worksheet.update('A1', data_str, value_input_option="USER_ENTERED")
        
        print(f"成功: {len(df)} 件のデータを {sheet_name} に書き込みました。")
    except Exception as e:
        print(f"エラー発生: {e}")

# ==========================================
# 処理2: 約束集計表
# ==========================================
async def run_appointment_aggregation():
    """処理2: 予約電話抽出 -> 約束集計表シート (ピボット集計・追記)"""
    print("\n--- [処理2] 約束集計表の実行を開始します ---")
    async with async_playwright() as p:
        browser, page = await login_and_get_page(p)
        
        try:
            print("本人確認状況(中分類)を『予約電話』に設定します...")
            await page.locator("#status_chu").select_option(label="予約電話")

            print("条件を絞り込みます...")
            await page.get_by_role("button", name="絞込").click()
            await page.wait_for_load_state("networkidle")

            print("CSVをダウンロードしています...")
            async with page.expect_download() as download_info:
                await page.get_by_role("button", name="CSV抽出").click()
            download = await download_info.value
            await download.save_as(CSV_TEMP_PATH)
            print(f"CSVを保存しました: {CSV_TEMP_PATH}")

            # ピボット集計してスプレッドシートへ追記
            await upload_pivot_to_sheet(SHEET_NAMES["aggregation"])

        finally:
            await browser.close()

async def upload_pivot_to_sheet(sheet_name):
    """CSVをピボット集計し、指定したシートの末尾に追記する関数 (処理2用)"""
    print(f"スプレッドシート「{sheet_name}」に集計データを追記しています...")
    try:
        # CSV読み込み
        df = pd.read_csv(CSV_TEMP_PATH, encoding="shift_jis")
        df = df.fillna("")

        # --- データ成形 ---
        # 「次回対応日」をdatetime型に変換
        df['次回対応日'] = pd.to_datetime(df['次回対応日'], errors='coerce')
        
        # --- 当日のみにフィルター (Pandasで実施) ---
        today_date = datetime.now().date()
        df = df[df['次回対応日'].dt.date == today_date]
        
        if df.empty:
            print("【通知】本日の日付に該当するデータがありませんでした。集計をスキップします。")
            return

        # 1時間単位に切り捨て (datetime型のまま保持)
        df['対応時間帯'] = df['次回対応日'].dt.floor('h')
        
        # --- 9:00から21:00までの全時間帯リストを作成 ---
        # 本日の日付の9:00から21:00までのRangeを作成
        start_time = datetime.combine(today_date, datetime.min.time()).replace(hour=9)
        end_time = datetime.combine(today_date, datetime.min.time()).replace(hour=21)
        all_hours = pd.date_range(start=start_time, end=end_time, freq='h')
        
        # ピボットテーブル作成 (縦軸: 本人確認状況, 横軸: 対応時間帯, 値: 件数)
        pivot_df = df.pivot_table(
            index='本人確認状況', 
            columns='対応時間帯', 
            values='次回対応日', 
            aggfunc='count', 
            fill_value=0
        )
        
        # 作成した全時間帯でリインデックス (データがない時間は0で埋める)
        pivot_df = pivot_df.reindex(columns=all_hours, fill_value=0)
        
        # ヘッダーを生成 (datetimeオブジェクトをスプレッドシートが日付として認識できる形式の文字列に変換)
        # 1列目はインデックス名
        headers = ['本人確認状況'] + [col.strftime('%Y/%m/%d %H:%M') for col in all_hours]
        
        # データをリスト化 (件数は数値のまま保持される)
        data_to_append = pivot_df.reset_index().values.tolist()
        
        # Google Sheets APIで末尾に追記
        gc = get_gspread_client()
        sh = gc.open_by_key(SHEET_ID)
        worksheet = sh.worksheet(sheet_name)
        
        # ヘッダーも含めて末尾に追記 (USER_ENTEREDにより日付文字列が自動的にシリアル値に変換される)
        worksheet.append_rows([headers] + data_to_append, value_input_option="USER_ENTERED")
        
        print(f"成功: 本日のデータを集計し {sheet_name} に追記しました。")
    except Exception as e:
        print(f"エラー発生: {e}")

# ==========================================
# メイン実行ルーチン
# ==========================================
async def main():
    try:
        # 処理1の実行
        await run_management_extraction()
        # 処理2の実行
        await run_appointment_aggregation()
        print("\n==========================================")
        print("すべての処理が正常に完了しました。")
        print("==========================================")
    except Exception as e:
        print(f"\n致命的なエラーが発生しました: {e}")

if __name__ == "__main__":
    asyncio.run(main())
