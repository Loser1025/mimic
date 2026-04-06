import os
import glob
import pandas as pd
from io import StringIO
from datetime import datetime

def get_latest_csv(pattern="visitor_data_*.csv"):
    """
    指定されたパターンに一致する最新のCSVファイルパスを返します。
    """
    files = glob.glob(pattern)
    if not files:
        return None
    # 更新日時が最新のものを返す
    return max(files, key=os.path.getctime)

def process_lstep_csv(file_path):
    """
    L-StepのCSVを読み込み、スプレッドシートの「登録数」シートに適合する形式に加工します。
    戻り値: [[日付, 数値], [日付, 数値], ...] の形式のリスト
    """
    if not file_path:
        raise FileNotFoundError("処理対象のCSVファイルが見つかりませんでした。")

    # L-Step CSVで想定されるエンコーディング
    encodings = ['utf-8-sig', 'shift_jis', 'cp932']
    df = None

    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                lines = f.readlines()
            
            # 「日付」または「登録日」という文字列が含まれる行をヘッダー行として特定する
            header_idx = -1
            for i, line in enumerate(lines):
                if any(kw in line for kw in ['日付', '登録日', '反響']):
                    header_idx = i
                    break
            
            if header_idx != -1:
                # ヘッダー行以降をデータとして読み込む
                csv_content = "".join(lines[header_idx:])
                df = pd.read_csv(StringIO(csv_content), encoding=enc)
                print(f"✅ CSVの読み込みに成功しました (Encoding: {enc}, Header line: {header_idx})")
                break
        except Exception as e:
            continue

    if df is None:
        raise ValueError("CSVファイルを正しく解析できませんでした。エンコーディングが不適切か、ヘッダー行が見つかりません。")

    # --- データ加工ロジック ---
    
    # 1. 必要な列の特定
    # 日付列を探す (日付, 登録日, 反響日)
    date_col = next((col for col in df.columns if any(kw in col for kw in ['日付', '登録日', '反響日'])), df.columns[0])
    # 登録数/反響数などの数値列を探す
    count_col = next((col for col in df.columns if any(kw in col for kw in ['登録数', '反響数', '数', '全体'])), df.columns[1])
    
    print(f"📊 抽出列: 日付={date_col}, 数値={count_col}")

    # 2. 必要な列のみ抽出
    df_processed = df[[date_col, count_col]].copy()

    # 3. クレンジング
    # 空行を削除
    df_processed = df_processed.dropna(subset=[date_col])

    # 日付形式を統一 (YYYY-MM-DD)
    try:
        df_processed[date_col] = pd.to_datetime(df_processed[date_col]).dt.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"⚠️ 日付変換でエラーが発生しました: {e}")

    # 数値列を整数に変換（カンマ除去などの処理を含む）
    df_processed[count_col] = (
        df_processed[count_col]
        .astype(str)
        .str.replace(',', '')
        .replace('nan', '0')
    )
    df_processed[count_col] = pd.to_numeric(df_processed[count_col], errors='coerce').fillna(0).astype(int)

    # 4. 「合計」などの集計行を除外 (日付列に数字以外が入っている行を消す)
    df_processed = df_processed[df_processed[date_col].str.contains(r'\d{4}-\d{2}-\d{2}', na=False)]

    # 5. 日付で昇順ソート
    df_processed = df_processed.sort_values(by=date_col)

    # Google Sheets API 用に 2次元リストに変換
    result = df_processed.values.tolist()
    
    print(f"✨ 加工完了: {len(result)} 件のデータを抽出しました。")
    return result

if __name__ == "__main__":
    # テスト実行
    try:
        latest_file = get_latest_csv()
        if latest_file:
            print(f"Testing with: {latest_file}")
            data = process_lstep_csv(latest_file)
            print("Sample data:", data[:5])
        else:
            print("❌ テスト用のCSVファイルが見つかりませんでした。先に download_csv.py を実行してください。")
    except Exception as e:
        print(f"❌ Error: {e}")
