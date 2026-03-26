"""
GASのgetSummaryData + constructPromptをPythonで再現してプロンプトを出力する
"""
import json
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_PATH = r'C:/Users/弁護士法人響/Downloads/ageless-impulse-488713-m6-0c52b81add54.json'
SPREADSHEET_ID = '1qw_aL8B9aJ_7Ad58qNxjNexTT20UOKU4LuUsjf3c6eQ'
SHEET_NAME = '商談アポ'

PHYSICAL_REASONS = ["代理権越え・法的相当", "案件化不可", "生活保護受給者", "質問のみ(依頼意志なし)", "短期・少額借入", "任意整理不可業者"]
IN_PROGRESS = ["#N/A", "(初期ヒアリング)", "(未通話)", "(面談予約)", "(商談中)", ""]

def build_service():
    creds = service_account.Credentials.from_service_account_file(
        SA_PATH, scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return build('sheets', 'v4', credentials=creds)

def main():
    service = build_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'"
    ).execute()
    values = result.get('values', [])

    # 行数確認
    print(f"取得行数: {len(values)}")

    def get(row, i, default=''):
        return str(row[i]).strip() if len(row) > i else default

    # 数値サマリー
    honkaku = int(get(values[2], 1) or 0) if len(values) > 2 else 0
    shodan  = int(get(values[3], 1) or 0) if len(values) > 3 else 0
    apo     = int(get(values[4], 1) or 0) if len(values) > 4 else 0
    teian   = int(get(values[5], 1) or 0) if len(values) > 5 else 0

    r_shodan = round(shodan / honkaku * 100, 1) if honkaku > 0 else 0
    r_apo_hk = round(apo / honkaku * 100, 1) if honkaku > 0 else 0

    def kpi(val, target):
        val = float(val)
        return "◎達成" if val >= target else ("△要注意" if val >= target - 3 else "×未達")

    summary_block = (
        f"【数値サマリー】\n━━━━━━━━━━━━\n"
        f"■本確：{honkaku}件\n"
        f"■商談：{shodan}件 ({r_shodan}% / 目標85%) {kpi(r_shodan, 85)}\n"
        f"■アポ：{apo}件 ({r_apo_hk}% / 目標66%) {kpi(r_apo_hk, 66)}\n"
        f"■提案：{teian}件"
    )

    # 9行目（index=8）をヘッダーとして列インデックスを動的取得
    header_row = values[8] if len(values) > 8 else []
    print(f"\n【9行目ヘッダー一覧】")
    for i, h in enumerate(header_row):
        if h:
            print(f"  [{i}] {h}")

    def col(name):
        for i, h in enumerate(header_row):
            if str(h).strip() == name:
                return i
        return -1

    def find_nth(name, n):
        count = 0
        for i, h in enumerate(header_row):
            if str(h).strip() == name:
                count += 1
                if count == n:
                    return i
        return -1

    i_staff_a  = col('担当')
    i_lp_a     = col('LP')
    i_reason_a = col('理由')
    i_remark_a = col('備考')
    i_staff_b  = find_nth('担当', 2)
    i_lp_b     = find_nth('LP', 2)
    i_reason_b = find_nth('理由', 2)
    i_remark_b = find_nth('備考', 2)

    print(f"\n【列検出結果】")
    print(f"  担当者A={i_staff_a}, LP-A={i_lp_a}, 理由A={i_reason_a}, 備考A={i_remark_a}")
    print(f"  担当者B={i_staff_b}, LP-B={i_lp_b}, 理由B={i_reason_b}, 備考B={i_remark_b}")

    staff_stats_a, staff_stats_b, lp_stats = {}, {}, {}
    impr_count_a, impr_count_b = 0, 0

    for i, row in enumerate(values[9:], start=9):
        id_ = get(row, 0)
        lp_a = get(row, i_lp_a) if i_lp_a >= 0 else ''
        lp_b = get(row, i_lp_b) if i_lp_b >= 0 else ''
        if lp_a: lp_stats[lp_a] = lp_stats.get(lp_a, 0) + 1
        if lp_b: lp_stats[lp_b] = lp_stats.get(lp_b, 0) + 1

        staff_a  = get(row, i_staff_a)  if i_staff_a  >= 0 else ''
        reason_a = get(row, i_reason_a) if i_reason_a >= 0 else ''
        remark_a = get(row, i_remark_a)[:150] if i_remark_a >= 0 else ''
        if staff_a and reason_a not in PHYSICAL_REASONS:
            impr_count_a += 1
            if staff_a not in staff_stats_a:
                staff_stats_a[staff_a] = {'count': 0, 'details': []}
            staff_stats_a[staff_a]['count'] += 1
            staff_stats_a[staff_a]['details'].append({'id': id_, 'reason': reason_a, 'remark': remark_a})

        staff_b  = get(row, i_staff_b)  if i_staff_b  >= 0 else ''
        reason_b = get(row, i_reason_b) if i_reason_b >= 0 else ''
        remark_b = get(row, i_remark_b)[:150] if i_remark_b >= 0 else ''
        if staff_b and reason_b not in IN_PROGRESS and reason_b not in PHYSICAL_REASONS:
            impr_count_b += 1
            if staff_b not in staff_stats_b:
                staff_stats_b[staff_b] = {'count': 0, 'details': []}
            staff_stats_b[staff_b]['count'] += 1
            staff_stats_b[staff_b]['details'].append({'id': id_, 'reason': reason_b, 'remark': remark_b})

    def format_staff(stats):
        lines = []
        for name in sorted(stats, key=lambda x: -stats[x]['count']):
            if stats[name]['count'] >= 2:
                logs = '\n'.join(f"[ID:{d['id']}] 理由:{d['reason']} / 備考:{d['remark']}" for d in stats[name]['details'])
                lines.append(f"【担当：{name}】{stats[name]['count']}件\n{logs}")
        return '\n\n'.join(lines) if lines else "（2件以上の該当なし）"

    lp_list = ' / '.join(f"{k}:{v}件" for k, v in lp_stats.items() if v >= 2)

    prompt = f"""あなたは弁護士事務所の営業アシスタントAIです。
LINE/Chatwork向けに、以下の構成でレポートを作成してください。

## 【データ情報】
数値：{summary_block}
改善可能失注：本確→商談 {impr_count_a}件 / 商談→アポ {impr_count_b}件
LP別発生：{lp_list}

## 担当者別詳細（分析用）
【本確→商談】
{format_staff(staff_stats_a)}
【商談→アポ】
{format_staff(staff_stats_b)}

---
## レポート作成指示

★ レポートのメインは「担当者別分析」と「失注理由別分析」。LP分析は最後に簡潔にまとめるだけでよい。

1. ▼ 失注理由別 深掘り（本確→商談 / 商談→アポ それぞれ）
・理由ごとに相談者の心理・共通パターンを分析。備考ログのID事例を具体的に引用。
・「初期ヒア前キャンセル」「デメリット懸念」「第三者相談中」など理由別に見出しを立てる。

2. ▼ 担当者別 傾向と課題（★メインコンテンツ）
・2件以上の失注がある担当者を全員、本確→商談・商談→アポ両方の観点で分析。
・備考ログに基づいた具体的な行動・心理の課題を記述。改善アドバイスも添える。
・LP情報は出さないこと。

3. ▼ LP別サマリー（簡潔に）
・媒体ごとの失注件数を箇条書きで列挙するだけでよい。深掘りは不要。

## 制約
・太字（**）は絶対に使用禁止。
・見出しは【 】や ▼、■ を使用し、改行を多用してスマホで見やすく。
・日本語で出力。"""

    out = Path(__file__).parent / 'prompt_output.txt'
    out.write_text(f"取得行数: {len(values)}\n\n{'='*60}\n【AIに送信されるプロンプト全文】\n{'='*60}\n{prompt}", encoding='utf-8')
    print(f"出力完了: {out}")

if __name__ == '__main__':
    main()
