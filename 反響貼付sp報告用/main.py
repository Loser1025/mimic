# -*- coding: utf-8 -*-
"""
対応履歴 + 転記（ローカル実行版）
- 『対応履歴』CSVから U,O,D をA:Cへ、Bは日付USER_ENTERED
- A列(ID)を R列に出力
- 転記：『貼り付け』『LINE新フロー』に加えて『きんつーん※(AG2:AO)』にも G3:O10002 を転記

【初回セットアップ】
1. pip install -r requirements.txt
2. Google Cloud Console で OAuth2.0クライアントID（デスクトップアプリ）を作成
3. JSONをダウンロードして credentials.json としてこのファイルと同じフォルダに置く
4. 初回実行時にブラウザが開くので Google アカウントで認証する（以降は自動）
"""

import re
import sys
import pandas as pd
from pathlib import Path
import gspread
from gspread_dataframe import set_with_dataframe
import tkinter as tk
from tkinter import filedialog

# =============================
# 設定
# =============================
SRC_SPREADSHEET_URL_OR_ID = "https://docs.google.com/spreadsheets/d/10vxqlRuyiQLup6kSJZlgf3Lv9v1L8IKVM329Eh5hVtE/edit"
SRC_SHEET_NAME = "シート1"

START_ROW = 3
SKIP_HEADER = True
CLEAR_BEFORE_WRITE = True

HISTORY_COLUMNS = ["U", "O", "D", "A"]

R_COL_LETTER = "R"
CLEAR_R_BEFORE_WRITE = True

COPY_RANGE_FOR_DST1 = "G3:O10002"

DST1_URL_OR_ID = "https://docs.google.com/spreadsheets/d/1gpo9fDhrjaIOkSE5zJyNMm8vIrRzpLmWdJNn_GLCwpo/edit"
DST1_SHEET = "貼り付け"
DST1_START_CELL = "AG2"
DST1_CLEAR_RANGE = "AG2:AO10024"

COPY_RANGE_FOR_DST2 = "AJ3:AK33"
DST2_URL_OR_ID = "https://docs.google.com/spreadsheets/d/1_WnmB2CM2IhHsx5WGCs1ykFXEshefVB5bpg09hImFEI/edit"
DST2_SHEET = "LINE新フロー"
DST2_START_CELL = "A65"
DST2_CLEAR_RANGE = "A65:B96"

DST3_URL_OR_ID = "https://docs.google.com/spreadsheets/d/1_WnmB2CM2IhHsx5WGCs1ykFXEshefVB5bpg09hImFEI/edit"
DST3_SHEET = "きんつーん※"
DST3_START_CELL = "AG2"
DST3_CLEAR_RANGE = "AG2:AO10024"

# credentials.json / token.json の保存場所（このスクリプトと同じフォルダ）
BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
TOKEN_FILE = BASE_DIR / "token.json"

# =============================
# CSV 読み込み
# =============================
ENCODINGS = [
    "utf-8-sig", "utf-8", "cp932", "shift_jis", "utf-16", "utf-16le", "utf-16be",
    "iso-2022-jp", "euc_jp", "latin-1",
]
SEPS = [None, ",", "\t", ";", "|"]

def read_csv_safely(path: Path) -> pd.DataFrame:
    last_err = None
    for enc in ENCODINGS:
        for sep in SEPS:
            try:
                return pd.read_csv(
                    path, header=None, dtype=str, encoding=enc,
                    engine="python", sep=sep, on_bad_lines="skip",
                )
            except Exception as e:
                last_err = e
    for enc in ENCODINGS:
        for sep in SEPS:
            try:
                return pd.read_csv(
                    path, header=None, dtype=str, encoding=enc,
                    engine="python", sep=sep, on_bad_lines="skip",
                    encoding_errors="replace",
                )
            except Exception as e:
                last_err = e
    raise RuntimeError(f"CSVの読み込みに失敗しました: {last_err}")

# =============================
# ユーティリティ
# =============================
def extract_id(url_or_id: str) -> str:
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", url_or_id)
    return m.group(1) if m else url_or_id.strip()

def open_sheet_anyway(gc: gspread.Client, url_or_id: str, sheet_name: str):
    key = extract_id(url_or_id)
    try:
        sh = gc.open_by_key(key)
    except Exception:
        sh = gc.open_by_url(url_or_id)
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(sheet_name, rows=20000, cols=300)
    return sh, ws

def col_letter_to_index(letter: str) -> int:
    s = letter.strip().upper()
    idx = 0
    for ch in s:
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1  # 0-based

def trim_trailing_empty_rows(matrix):
    trimmed = list(matrix)
    while trimmed and all((c is None or str(c) == "") for c in trimmed[-1]):
        trimmed.pop()
    return trimmed

# =============================
# メイン処理
# =============================
def main():
    # --- ファイル選択ダイアログ ---
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    print("📂 対応履歴CSVを選択してください（複数選択可）...")
    file_paths = filedialog.askopenfilenames(
        title="対応履歴CSVを選択（複数可）",
        filetypes=[("CSVファイル", "*.csv"), ("すべてのファイル", "*.*")],
    )

    if not file_paths:
        print("❌ ファイルが選択されていません。終了します。")
        sys.exit(0)

    # --- Google 認証 ---
    if not CREDENTIALS_FILE.exists():
        print(f"❌ credentials.json が見つかりません: {CREDENTIALS_FILE}")
        print("   Google Cloud Console で OAuth2.0クライアントID（デスクトップアプリ）を作成し、")
        print("   JSONをダウンロードして credentials.json としてスクリプトと同じフォルダに置いてください。")
        sys.exit(1)

    print("🔐 Google認証中（初回はブラウザが開きます）...")
    gc = gspread.oauth(
        credentials_filename=str(CREDENTIALS_FILE),
        authorized_user_filename=str(TOKEN_FILE),
    )

    # --- CSV 分類・読み込み ---
    history_dfs = []
    history_files = []

    for file_path in file_paths:
        filename = Path(file_path).name
        if "対応履歴" in filename:
            df = read_csv_safely(Path(file_path))
            if SKIP_HEADER and len(df) > 0:
                df = df.iloc[1:].reset_index(drop=True)

            cols = []
            for col in HISTORY_COLUMNS:
                idx = col_letter_to_index(col)
                cols.append(
                    df.iloc[:, idx].fillna("") if idx < df.shape[1]
                    else pd.Series([""] * len(df))
                )
            hdf = pd.concat(cols, axis=1)
            hdf.columns = ["U", "O", "D", "A"]
            history_dfs.append(hdf)
            history_files.append(filename)
        else:
            print(f"⚠️  スキップ（ファイル名に「対応履歴」が含まれません）: {filename}")

    if not history_dfs:
        print("❌ 中止：対応履歴データが見つかりません。")
        sys.exit(0)

    # --- シート接続 ---
    print("📊 スプレッドシートに接続中...")
    _, src_ws = open_sheet_anyway(gc, SRC_SPREADSHEET_URL_OR_ID, SRC_SHEET_NAME)

    out_df = pd.concat(history_dfs, axis=0, ignore_index=True)
    mask_not_all_empty = ~(out_df.replace("", pd.NA).isna().all(axis=1))
    out_df = out_df[mask_not_all_empty].reset_index(drop=True)

    # A:C クリア＆書き出し
    if CLEAR_BEFORE_WRITE:
        try:
            src_ws.batch_clear([f"A{START_ROW}:C"])
        except Exception:
            pass

    set_with_dataframe(
        src_ws, out_df[["U", "O", "D"]],
        row=START_ROW, col=1,
        include_index=False, include_column_header=False,
    )

    # B列: 日時（USER_ENTERED）
    b_series = pd.to_datetime(out_df["O"], errors="coerce")
    b_str = b_series.dt.strftime("%Y/%m/%d %H:%M").fillna("").tolist()
    if b_str:
        b_end = START_ROW + len(b_str) - 1
        src_ws.update(
            f"B{START_ROW}:B{b_end}",
            [[v] for v in b_str],
            value_input_option="USER_ENTERED",
        )

    # R列: ID
    id_list = out_df["A"].astype(str).tolist()
    r_vals = id_list[:]
    while r_vals and r_vals[-1] == "":
        r_vals.pop()
    if CLEAR_R_BEFORE_WRITE:
        try:
            src_ws.batch_clear([f"{R_COL_LETTER}{START_ROW}:{R_COL_LETTER}"])
        except Exception:
            pass
    if r_vals:
        r_end = START_ROW + len(r_vals) - 1
        src_ws.update(
            f"{R_COL_LETTER}{START_ROW}:{R_COL_LETTER}{r_end}",
            [[v] for v in r_vals],
            value_input_option="USER_ENTERED",
        )

    print(f"🟢 書き出し完了：対応履歴 {len(history_files)}件を反映（A:C=U,O,D／Bは日時USER_ENTERED／R=A[ID]）。")

    # --- 転記 ---
    print("📋 転記中...")

    # G3:O10002 取得（宛先1・3で共用）
    matrix1 = src_ws.get(COPY_RANGE_FOR_DST1)
    matrix1 = trim_trailing_empty_rows(matrix1)

    # 宛先1：貼り付け AG2〜
    print("  → 貼り付け シート...")
    _, dst1_ws = open_sheet_anyway(gc, DST1_URL_OR_ID, DST1_SHEET)
    try:
        dst1_ws.batch_clear([DST1_CLEAR_RANGE])
    except Exception:
        pass
    if matrix1:
        dst1_ws.update(DST1_START_CELL, matrix1, value_input_option="USER_ENTERED")

    # 宛先3：きんつーん※ AG2〜
    print("  → きんつーん※ シート...")
    _, dst3_ws = open_sheet_anyway(gc, DST3_URL_OR_ID, DST3_SHEET)
    try:
        dst3_ws.batch_clear([DST3_CLEAR_RANGE])
    except Exception:
        pass
    if matrix1:
        dst3_ws.update(DST3_START_CELL, matrix1, value_input_option="USER_ENTERED")

    # 宛先2：LINE新フロー A65〜（AJ3:AK33 を別取得）
    print("  → LINE新フロー シート...")
    matrix2 = src_ws.get(COPY_RANGE_FOR_DST2)
    _, dst2_ws = open_sheet_anyway(gc, DST2_URL_OR_ID, DST2_SHEET)
    try:
        dst2_ws.batch_clear([DST2_CLEAR_RANGE])
    except Exception:
        pass
    if matrix2:
        dst2_ws.update(DST2_START_CELL, matrix2, value_input_option="USER_ENTERED")

    print("✅ 完了：『貼り付け』AG2〜、『きんつーん※』AG2〜、『LINE新フロー』A65〜 へ転記しました。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n中断されました。")
    except Exception as e:
        print(f"\n❌ エラーが発生しました: {e}")
        raise
    finally:
        input("\nEnterキーを押して終了...")
