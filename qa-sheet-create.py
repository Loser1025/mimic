import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY = 'C:/Users/弁護士法人響/Downloads/ageless-impulse-488713-m6-0c52b81add54.json'
SSID = '1uwuYAu-4320uPrACJFf6VwzRl_M6k-RtOl9oKCREF38'
GID = 1410199565  # Q＆A sheet

creds = service_account.Credentials.from_service_account_file(
    SA_KEY, scopes=['https://www.googleapis.com/auth/spreadsheets']
)
service = build('sheets', 'v4', credentials=creds)

# ── Q&Aデータ ──────────────────────────────────────────────
QA_DATA = [
    # ヘッダー
    ['カテゴリ', 'よくある質問（お客様の言葉）', '回答スクリプト', 'ポイント・注意'],

    # ─ サービス・事務所について ─
    ['サービス・事務所', 'どこの会社ですか？何の電話ですか？',
     'こちら司法書士法人奏と申します。先日LINEの借金減額シミュレーションをご利用いただいた方のお電話番号にご連絡しております。お間違いないでしょうか？',
     'LINEシミュレーター利用者への架電であることを明確に'],
    ['サービス・事務所', '電話相談は無料ですか？',
     'はい、本日のお電話相談は完全無料でございます。どうぞご安心ください。',
     '冒頭のオープニングで必ず伝える'],
    ['サービス・事務所', '弁護士と司法書士は何が違うのですか？',
     '司法書士も弁護士と同様に債務整理を行うことができます。任意整理・個人再生・自己破産すべてご対応可能でございます。',
     '過度な比較はせず「どちらも対応可能」で収める'],
    ['サービス・事務所', '複数の事務所から電話が来るのはなぜですか？',
     '弊所はいくつかグループ会社がございますので、受付によって事務所名が変わる場合がございます。いずれも同じグループでございますのでご安心ください。',
     '冒頭のオープニングで先に説明しておく'],

    # ─ 手続きの種類 ─
    ['手続きの種類', '任意整理・個人再生・自己破産の違いを教えてください',
     '大きく3つございます。①任意整理：利息カット＋分割返済、②個人再生：借金を大幅に減額、③自己破産：返済が免除。どれが合っているかは状況次第ですので、専門家が詳しくご案内いたします。',
     '詳細は面談員に引き継ぐ。FL課は概要のみ'],
    ['手続きの種類', '過払い金は戻ってきますか？',
     '2010年以前から高金利で借りていた方は、払い過ぎた利息が戻ってくる可能性がございます。ご利用期間や金利を確認する必要がありますので、一度ご状況を確認させてください。',
     '借入期間が長い（10年以上）方は可能性あり'],
    ['手続きの種類', 'どれくらい減額できますか？',
     '〇〇様のご状況から減額できる可能性は十分うかがえております。具体的にどれくらい減るかは専門家が計算してご案内いたします。まずはご状況を詳しくお聞かせください。',
     '具体的な金額は言わない。面談員に繋ぐ'],

    # ─ 影響・デメリット ─
    ['影響・デメリット', '家族にバレますか？知られたくないのですが',
     '任意整理であれば、官報への掲載もなく、ご家族への通知もございません。手続き中は弊所が窓口になりますので、直接ご連絡が来ることもほとんどなくなります。',
     '手続き種類によって異なる。個人再生・破産は官報掲載あり（一般の方はほぼ見ない）'],
    ['影響・デメリット', '職場にバレますか？仕事に影響しますか？',
     '会社員の方は基本的に職場に通知されることはありません。ただし公務員・士業・警備員の方は自己破産の場合に一時的に影響が出る場合がございます。〇〇様のお仕事は何をされていますか？',
     '職種確認を忘れずに。問題があれば面談員に引き継ぐ'],
    ['影響・デメリット', 'クレジットカードは使えなくなりますか？',
     '手続き後は一定期間（5〜10年程度）、新たなお借入れやクレジットカードの作成が難しくなります。ただし既にカードのご利用が難しい状況であれば、借金を整理して生活を立て直される方が多いです。',
     'ブラックリスト（信用情報）について正確に説明する'],
    ['影響・デメリット', '保証人に影響しますか？',
     '保証人がいらっしゃるお借入れを整理対象にすると、保証人の方に請求が行く場合があります。保証人のいるお借入れは対象から外すことも選択できますので、ご状況をお聞かせください。',
     '保証人の有無を必ずヒアリングで確認する'],
    ['影響・デメリット', '持ち家・車はどうなりますか？',
     '任意整理の場合、基本的に財産への影響はほとんどありません。自己破産の場合は一定以上の財産が対象になりますが、生活に必要なものは残せます。住宅ローンがある場合は住宅ローン特則という選択肢もございます。',
     '持ち家・住宅ローン有無はヒアリングで確認済みのはず'],

    # ─ 費用・お金 ─
    ['費用・お金', '費用はいくらかかりますか？',
     '費用は実際に減額できた後に発生するものですので、まず無料でご状況を確認させてください。具体的な費用は専門家が詳しくご説明いたします。',
     '具体的金額は面談員が説明。FL課は「減額後に発生」のみ'],
    ['費用・お金', '今お金がなくても手続きできますか？',
     'はい、分割払いでのご対応も可能でございます。まずはご状況を確認させていただいた上で、無理のない形でご提案いたします。',
     '「お金がない」は断り文句の場合もある。温度感を確認'],

    # ─ 断り文句・反論対応 ─
    ['断り文句', '今は時間がないです・忙しいです',
     'かしこまりました。では何時頃であればお時間いただけますでしょうか？改めてご連絡いたします。',
     '折り返し時間を確認する。押しすぎない'],
    ['断り文句', '考えてみます・検討します',
     '〇〇様が今一番お困りのことは、毎月の返済が苦しいことでしたよね。考えている間にも利息は増えてしまいますので、まずお話だけでも聞いていただけますでしょうか？',
     'ニーズを再確認して温度感を上げる'],
    ['断り文句', '家族に相談してから決めます',
     'もちろんです。ご家族への相談は大切ですよね。ちなみに今の状況はご家族はご存知でしょうか？よろしければ今概要だけお聞きいただき、その内容をご家族に共有していただく形でも良いかと思いますが、いかがでしょうか？',
     'まず話を聞いてもらうことを優先する'],
    ['断り文句', '知り合いに聞きます・他のところで相談します',
     'もちろんです。いろいろ比べてみることは大切ですよね。弊所は相談は完全無料ですし、無理に進めることはございませんので、まず一度ご状況を確認させていただいてもよろしいでしょうか？',
     '否定せず、まず話を聞いてもらうことを目指す'],
    ['断り文句', '登録した覚えがない・電話番号はどこで？',
     '先日、借金減額シミュレーションというサービスをご利用いただいた際にご登録いただいた番号です。もしよければ今のご状況を無料でお聞きすることもできますが、いかがでしょうか？',
     '強引に進めない。試しにやっただけの方も多い'],
    ['断り文句', 'もう解決しました・大丈夫です',
     'それは良かったです。もし今後また何かお困りのことがございましたら、いつでもご相談ください。失礼いたしました。',
     'すっきり終わる。引き留めない'],
    ['断り文句', 'もう電話しないでください',
     'かしこまりました。大変失礼いたしました。以後ご連絡しないよう対応いたします。本日は失礼いたしました。',
     '番号をDNDに登録する'],

    # ─ 手続き中・手続き後 ─
    ['手続き中・後', '手続き中も返済が必要ですか？',
     '任意整理の手続き中は、弊所が各業者と交渉している間は一時的に返済をストップしていただく場合があります。詳細は専門家からご説明いたします。',
     'FL課は概要のみ。詳細は面談員へ'],
    ['手続き中・後', '手続きにはどれくらいかかりますか？',
     '任意整理であれば概ね3〜6ヶ月程度で各業者との和解が完了し、その後分割返済に入る流れが多いです。ただし状況によって異なりますので、専門家から詳しくご説明いたします。',
     '具体期間は目安のみ。断言しない'],
]

# ── Step 1: データ書き込み ────────────────────────────────
service.spreadsheets().values().batchUpdate(
    spreadsheetId=SSID,
    body={'valueInputOption': 'RAW', 'data': [{'range': 'Q\uff06A!A1', 'values': QA_DATA}]}
).execute()
print(f'✓ データ書き込み完了（{len(QA_DATA)}行）')

# ── Step 2: 書式設定 ─────────────────────────────────────
def rgb(h):
    h = h.lstrip('#')
    return {'red': int(h[0:2],16)/255, 'green': int(h[2:4],16)/255, 'blue': int(h[4:6],16)/255}

cat_colors = {
    'サービス・事務所': rgb('D9EAD3'),  # 薄緑
    '手続きの種類':     rgb('CCE2F5'),  # 薄青
    '影響・デメリット': rgb('FFF2CC'),  # 薄黄
    '費用・お金':       rgb('EAD1F5'),  # 薄紫
    '断り文句':         rgb('FFD9CC'),  # 薄オレンジ
    '手続き中・後':     rgb('D0F4F4'),  # 薄シアン
}

HEADER_BG   = rgb('2A6279')
HEADER_TEXT = rgb('FFFFFF')

requests = []

# ① 全体ベース書式（wrap + 上揃え）
requests.append({'repeatCell': {
    'range': {'sheetId': GID, 'startRowIndex': 0, 'endRowIndex': 50, 'startColumnIndex': 0, 'endColumnIndex': 4},
    'cell': {'userEnteredFormat': {
        'wrapStrategy': 'WRAP',
        'verticalAlignment': 'TOP',
        'textFormat': {'fontSize': 10}
    }},
    'fields': 'userEnteredFormat(wrapStrategy,verticalAlignment,textFormat)'
}})

# ② ヘッダー行
requests.append({'repeatCell': {
    'range': {'sheetId': GID, 'startRowIndex': 0, 'endRowIndex': 1, 'startColumnIndex': 0, 'endColumnIndex': 4},
    'cell': {'userEnteredFormat': {
        'backgroundColor': HEADER_BG,
        'textFormat': {'bold': True, 'fontSize': 11, 'foregroundColor': HEADER_TEXT},
        'horizontalAlignment': 'CENTER',
        'verticalAlignment': 'MIDDLE',
    }},
    'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)'
}})

# ③ カテゴリ別背景色（データ行）
for i, row in enumerate(QA_DATA):
    if i == 0:
        continue
    cat = row[0]
    if cat in cat_colors:
        requests.append({'repeatCell': {
            'range': {'sheetId': GID, 'startRowIndex': i, 'endRowIndex': i+1, 'startColumnIndex': 0, 'endColumnIndex': 4},
            'cell': {'userEnteredFormat': {'backgroundColor': cat_colors[cat]}},
            'fields': 'userEnteredFormat.backgroundColor'
        }})

# ④ A列（カテゴリ）：中央揃え・太字
requests.append({'repeatCell': {
    'range': {'sheetId': GID, 'startRowIndex': 1, 'endRowIndex': len(QA_DATA), 'startColumnIndex': 0, 'endColumnIndex': 1},
    'cell': {'userEnteredFormat': {
        'horizontalAlignment': 'CENTER',
        'verticalAlignment': 'MIDDLE',
        'textFormat': {'bold': True}
    }},
    'fields': 'userEnteredFormat(horizontalAlignment,verticalAlignment,textFormat)'
}})

# ⑤ B列（Q）：太字
requests.append({'repeatCell': {
    'range': {'sheetId': GID, 'startRowIndex': 1, 'endRowIndex': len(QA_DATA), 'startColumnIndex': 1, 'endColumnIndex': 2},
    'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
    'fields': 'userEnteredFormat.textFormat'
}})

# ⑥ 列幅
for col_idx, px in enumerate([130, 280, 480, 220]):
    requests.append({'updateDimensionProperties': {
        'range': {'sheetId': GID, 'dimension': 'COLUMNS', 'startIndex': col_idx, 'endIndex': col_idx+1},
        'properties': {'pixelSize': px}, 'fields': 'pixelSize'
    }})

# ⑦ ヘッダー行高さ
requests.append({'updateDimensionProperties': {
    'range': {'sheetId': GID, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1},
    'properties': {'pixelSize': 40}, 'fields': 'pixelSize'
}})

# ⑧ データ行高さ
requests.append({'updateDimensionProperties': {
    'range': {'sheetId': GID, 'dimension': 'ROWS', 'startIndex': 1, 'endIndex': len(QA_DATA)},
    'properties': {'pixelSize': 85}, 'fields': 'pixelSize'
}})

# ⑨ 枠線
requests.append({'updateBorders': {
    'range': {'sheetId': GID, 'startRowIndex': 0, 'endRowIndex': len(QA_DATA), 'startColumnIndex': 0, 'endColumnIndex': 4},
    'innerHorizontal': {'style': 'SOLID',        'color': rgb('AAAAAA')},
    'innerVertical':   {'style': 'SOLID',        'color': rgb('AAAAAA')},
    'top':             {'style': 'SOLID_MEDIUM', 'color': HEADER_BG},
    'bottom':          {'style': 'SOLID_MEDIUM', 'color': HEADER_BG},
    'left':            {'style': 'SOLID_MEDIUM', 'color': HEADER_BG},
    'right':           {'style': 'SOLID_MEDIUM', 'color': HEADER_BG},
}})

# ⑩ ヘッダー固定
requests.append({'updateSheetProperties': {
    'properties': {'sheetId': GID, 'gridProperties': {'frozenRowCount': 1}},
    'fields': 'gridProperties.frozenRowCount'
}})

# ⑪ フィルター
requests.append({'setBasicFilter': {
    'filter': {
        'range': {'sheetId': GID, 'startRowIndex': 0, 'endRowIndex': len(QA_DATA), 'startColumnIndex': 0, 'endColumnIndex': 4}
    }
}})

result = service.spreadsheets().batchUpdate(
    spreadsheetId=SSID, body={'requests': requests}
).execute()
print(f'✓ 書式設定完了（{len(requests)}リクエスト）')
print('完了！')
