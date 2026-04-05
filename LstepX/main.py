import os
import time
import logging
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# 内部モジュールのインポート
from process_csv import process_lstep_csv
from upload_to_sheets import upload_to_google_sheets

# ================= 設定領域 =================
CONFIG = {
    "USER_ID": "kogawa_flka",
    "PASSWORD": "kogawa0930",
    "DOWNLOAD_DIR": r"C:\Users\Loser\Desktop\-\-\LstepX\downloads",
    "LOGIN_URL": "https://manager.linestep.net/account/login",
    "SPREADSHEET_ID": "1EmVvi7TwjrTc5Mx9wZjqo8G0ZCDrULUqPiD9oeDd97Y",
    "TARGET_SHEET": "登録数",
    "MAX_RETRIES": 3,
    "RETRY_DELAY": 5 # 初回リトライ待機秒数
}

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("automation.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# ============================================

def setup_driver():
    """Selenium WebDriverの設定"""
    try:
        if not os.path.exists(CONFIG["DOWNLOAD_DIR"]):
            os.makedirs(CONFIG["DOWNLOAD_DIR"])

        chrome_options = Options()
        prefs = {
            "download.default_directory": CONFIG["DOWNLOAD_DIR"],
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True
        }
        chrome_options.add_experimental_option("prefs", prefs)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        logger.info("WebDriverのセットアップが完了しました。")
        return driver
    except Exception as e:
        logger.error(f"WebDriverの起動に失敗しました: {e}")
        raise

def wait_for_download_complete(timeout=60):
    """ファイルがダウンロードされるまで待機し、最新のCSVパスを返す"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        files = os.listdir(CONFIG["DOWNLOAD_DIR"])
        csv_files = [f for f in files if f.endswith('.csv') and not f.startswith('chrome_download')]
        if csv_files:
            # 最新のファイルを取得
            latest_csv = max([os.path.join(CONFIG["DOWNLOAD_DIR"], f) for f in csv_files], key=os.path.getctime)
            logger.info(f"ファイルのダウンロードを確認しました: {latest_csv}")
            return latest_csv
        time.sleep(2)
    raise TimeoutException("CSVファイルのダウンロードがタイムアウトしました。")

def download_csv(driver):
    """LstepXからCSVをダウンロードするフロー"""
    wait = WebDriverWait(driver, 20)
    
    try:
        logger.info("ログインページにアクセス中...")
        driver.get(CONFIG["LOGIN_URL"])

        # ログイン入力
        wait.until(EC.presence_of_element_located((By.NAME, "user_id"))).send_keys(CONFIG["USER_ID"])
        driver.find_element(By.NAME, "password").send_keys(CONFIG["PASSWORD"])

        logger.info("reCAPTCHAの処理を開始します...")
        try:
            # iframeへの切り替え
            captcha_iframe = wait.until(EC.presence_of_element_located((By.XPATH, "//iframe[contains(@title, 'reCAPTCHA')]")))
            driver.switch_to.frame(captcha_iframe)
            checkbox = driver.find_element(By.ID, "recaptcha-anchor")
            checkbox.click()
            driver.switch_to.default_content()
            logger.info("reCAPTCHAのチェックボックスをクリックしました。")
        except (TimeoutException, NoSuchElementException):
            logger.warning("reCAPTCHAの自動クリックに失敗しました。手動で解決してください。")
            input(">>> ブラウザでreCAPTCHAを完了させ、『ログイン』ボタンを押す直前まで進めてから、ここでEnterキーを押してください...")

        # ログイン実行
        driver.find_element(By.XPATH, "//input[@value='ログイン']").click()

        logger.info("分析メニューへ移動中...")
        wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "クロス分析"))).click()
        wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "反響数？"))).click()

        logger.info("抽出条件を設定中...")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), '日付選択(終点)')]"))).click()
        # 5日を選択
        wait.until(EC.element_to_be_clickable((By.XPATH, "//td[text()='5']"))).click()
        driver.find_element(By.XPATH, "//input[@value='分析登録']").click()

        logger.info("CSVをエクスポート中...")
        analysis_btn = wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "分析を表示する")))
        analysis_btn.click()

        # ウィンドウ切り替え
        driver.switch_to.window(driver.window_handles[-1])
        
        # 再計算
        wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '再計算')]"))).click()
        time.sleep(3) # 計算処理待ち

        # エクスポート
        wait.until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "CSVエクスポート"))).click()
        
        return wait_for_download_complete()

    except (TimeoutException, NoSuchElementException) as e:
        logger.error(f"UI要素が見つかりませんでした。Lstepの画面仕様が変更された可能性があります: {e}")
        raise
    except WebDriverException as e:
        logger.error(f"ブラウザ操作中にエラーが発生しました: {e}")
        raise

def safe_upload_to_sheets(data):
    """API制限を考慮してリトライしながらアップロードする"""
    attempt = 0
    while attempt < CONFIG["MAX_RETRIES"]:
        try:
            upload_to_google_sheets(data)
            logger.info("Googleスプレッドシートへのアップロードが正常に完了しました。")
            return True
        except Exception as e:
            attempt += 1
            wait_time = CONFIG["RETRY_DELAY"] * (2 ** (attempt - 1)) + random.uniform(0, 1)
            logger.warning(f"アップロード失敗 (試行 {attempt}/{CONFIG['MAX_RETRIES']}): {e}")
            if attempt < CONFIG["MAX_RETRIES"]:
                logger.info(f"{wait_time:.2f}秒後にリトライします...")
                time.sleep(wait_time)
            else:
                logger.error("最大リトライ回数に達しました。アップロードを断念します。")
                raise e

def main():
    driver = None
    try:
        # 1. CSV取得
        driver = setup_driver()
        csv_path = download_csv(driver)
        logger.info(f"CSV取得成功: {csv_path}")

        # 2. データ加工
        logger.info("データを加工中...")
        processed_data = process_lstep_csv(csv_path)
        if not processed_data:
            raise ValueError("加工後のデータが空です。CSVの内容を確認してください。")
        logger.info(f"データ加工完了。行数: {len(processed_data)}")

        # 3. スプレッドシートへ書き込み (リトライ付き)
        logger.info("Googleスプレッドシートへアップロード中...")
        safe_upload_to_sheets(processed_data)

        logger.info("\n====================================================")
        logger.info("🎉 すべての工程が正常に完了しました！")
        logger.info("====================================================")

    except KeyboardInterrupt:
        logger.info("ユーザーによって処理が中断されました。")
    except Exception as e:
        logger.critical(f"致命的なエラーが発生し、処理を停止しました: {e}", exc_info=True)
    finally:
        if driver:
            driver.quit()
            logger.info("ブラウザを閉じました。")

if __name__ == "__main__":
    main()
