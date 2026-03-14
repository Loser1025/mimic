import asyncio
import re
from playwright.async_api import async_playwright
from datetime import datetime

# ────────────────────────────────────────
# 逆引きテーブル（履歴の表示テキスト → フォーム送信値）
# ────────────────────────────────────────
REVERSE = {
    'mst_contact_status_id': {
        '未通話': '101', '初期ヒアリング': '102', '提案中': '103', '面談予約': '104',
        '契約書送信済み': '105', '書説済／返送待ち': '106', '書戻り': '107',
        '面談設定中': '123', '面談設定保留': '120', '面談設定済み': '108',
        '面談リスケ中': '109', '面談後保留': '110', '面談後否決': '111',
        '受任': '112', '終了': '113', '提案終了': '122', '終了(架電禁止)': '114',
        '紹介中': '115', '紹介面談予約': '116', '紹介書戻り': '117',
        '紹介受任': '118', '相談者化': '119',
    },
    'contact_tool_type': {
        '(未選択)': '1', '電話': '2', '電話＋SMS': '11', 'SMS': '4',
        'SMS(一斉)': '12', 'メール': '3', '面談': '5', 'LINE': '6',
        '書類発送': '7', '秘書': '8', 'FAX': '9', 'その他': '10',
    },
    'contact_direction_type': {
        '未選択': '1', '受信': '2', '発信': '3',
    },
    'reason': {
        '(未通話)': '101', '(初期ヒアリング)': '151', '(面談予約)': '102',
        '(書戻り)': '103', '(面談設定保留)': '150', '(受任)': '104',
        'サンクス返信あり': '137', 'シミュ初回SMS送信': '138', 'シミュ初回SMS返信あり': '139',
        '通話アポ獲得': '143', 'フォーム予約': '161', '連絡先不備・間違い電話': '132',
        '初期ヒア前キャンセル': '146', 'アンケート・ポイント': '162', '外国人全般': '147',
        '債務整理以外の反響': '152', '質問のみ(依頼意志なし)': '105', '生活保護受給者': '111',
        '案件化不可': '153', '短期・少額借入': '154', '自己解決可能': '113',
        '代理権越え・法的相当': '145', '任意整理不可業者': '155', 'デメリット懸念': '156',
        '積立・返済不能': '157', '第三者相談中': '158', '相談者検討中': '159',
        '遠方で面談できず': '121', '債務整理拒否(理由不明)': '125',
        '提案後他社依頼': '160', '苦情等': '118',
    },
    'mst_consulter_next_action_id': {
        '(新規)日時指定架電': '117', 'フォロー１': '101', '提案': '116', 'メール送信': '119',
        'シミュ初回SMS送信': '120', 'SMS送信': '121', '(既存)日時指定架電': '118',
        'フォロー２': '102', '提案アポ1': '215', '提案アポ2': '216',
        'フォロー３': '103', 'フォロー４': '104', 'フォロー５': '105',
        'フォロー６': '106', 'フォロー７': '107', 'フォロー８': '108',
        'フォロー９': '109', 'フォロー１０': '110', 'フォロー１１': '111',
        'フォロー１２': '112', 'フォロー１３': '113', 'フォロー１４': '114',
        'フォロー１５': '115', 'AC2': '152', 'AC3': '153', 'AC4': '154',
        'AC5': '155', 'AC6': '156', 'AC7': '157', 'AC8': '158', 'AC9': '159',
        'AC10': '174', '契約書等送信': '122',
        '身分証等督促１': '130', '身分証等督促２': '131', '身分証等督促３': '132',
        '身分証等督促４': '133', '身分証等督促５': '134', '身分証等督促６': '135',
        '身分証等督促最後': '136', '面談予約後フォロー': '137',
        '書類督促１': '123', '書類督促２': '124', '書類督促３': '125',
        '書類督促４': '126', '書類督促５': '127', '書類督促６': '128', '書類督促最後': '129',
        '書類戻り後フォロー１': '138', '書類戻り後フォロー２': '139', '書類戻り後フォロー３': '140',
        '書類戻り後フォロー４': '141', '書類戻り後フォロー５': '142', '書類戻り後フォロー６': '143',
        '書類戻り後フォロー最後': '144', '面談設定': '145', '面談日前連絡': '146',
        '来所面談': '147', 'オンライン動画面談': '148', '電話面談': '149',
        '電話面談(日時指定あり)': '171', '法的チーム対応１': '170', '掘り起し': '175',
        '対応不要': '151', 'エラー確認': '176', 'SMS送信(優先)': '177',
        'LINE通話まち': '178', '掘り起し②': '182', '掘り起し③': '183', 'LINE送信': '185',
        '既存フォロー１': '189', '既存フォロー２': '190', '既存フォロー３': '191',
        '既存フォロー４': '192', '既存フォロー５': '193', '既存フォロー６': '194',
        '提案フォロー１': '198', '提案フォロー２': '199', '提案フォロー３': '200',
        '提案（日時指定架電）': '213',
    },
}

# user_id 逆引き（表示名 → ID）
USER_REVERSE = {
    "和田 浩典":"2001594","島田 雄左":"2001082","三ヶ㞍 勇輝":"2001083","鶴澤 大輔":"2001084",
    "宮城 誠":"2001108","岩間 俊樹":"2001111","牛山 定彦":"2001141","渡邊 倫子":"2001146",
    "卯都木 大":"2001175","高岡 宏":"2001180","齋藤 崇幸":"2001189","小山 菜々":"2001202",
    "中原 亮":"2001239","杉浦 尚武":"2001351","中町 遥":"2001240","瀧澤 和貴":"2001352",
    "尾﨑 友美":"2001310","佐藤 和雄":"2001424","治久丸 啓太":"2001476","増澤 千代":"2001528",
    "神 達也":"2001529","佐野 光":"2001552","佐々木 孝洋":"2001571","山重 和信":"2001574",
    "吉村 文菜":"2001575","三浦 和弥":"2001593","望月 純":"2002014","圓谷 修宏":"2001628",
    "山本 浩之":"2001695","大澤 愛歌":"2001701","志水 友行":"2001737","田嶋 剛":"2001738",
    "矢嶋 あゆみ":"2001805","井町 雅一":"2001745","篠崎 雅一":"2001812","渡邉 瑞人":"2001828",
    "芦澤 明子":"2001833","阿形 岳志":"2001845","須永 哲次":"2001936","増岡 隆夫":"2001793",
    "南竹 素聡":"2001943","佐々木 征和":"2002130","大橋 大武":"2002106","根本 和音":"2002107",
    "松島 俊介":"2001086","高橋 智奈":"2001104","髙橋 祥一朗":"2001112","金成 朋恵":"2001145",
    "仲松 菜奈子":"2001169","副島 翔太":"2001170","村上 進一":"2001194","河村 莉子":"2001241",
    "中村 真友子":"2001245","和久井 尚":"2001246","保坂 勇太":"2001247","広瀬 貴大":"2001248",
    "島崎 愛":"2001252","齊藤 史也":"2001277","天笠 芹菜":"2001291","林 聡美":"2001292",
    "宿南 彩子":"2001293","福田 美佐":"2001295","宇野 優萌":"2001298","藤野 真由美":"2001299",
    "比企 康子":"2001301","武藤 佳菜子":"2001302","秋山 佑衣":"2001312","糟谷 優":"2001317",
    "田中 晴香":"2001178","髙村 直樹":"2001337","横山 舞乃":"2001338","岡口 知生":"2001345",
    "熊手 夢見":"2001364","和田 牧夫":"2001366","内田 香織":"2001367","中山 雄貴":"2001382",
    "和田 有可":"2001396","高橋 優斗":"2001397","森田 菜摘":"2001402","内山 小夜子":"2001405",
    "常盤 奈美":"2001413","林 孝一郎":"2001420","染井 菜沙":"2001433","廣田 珠輝":"2001432",
    "山田 凛音":"2001458","平松 優希":"2001470","橋本 晴海":"2001474","川本 さつき":"2001490",
    "白窪 早":"2001491","綿引 一馬":"2001493","奥田 沙貴":"2001494","人見 真子":"2001501",
    "松戸 有彩":"2001504","水谷 史保":"2001508","吉松 舞香":"2001509","竹村 良太":"2001519",
    "仲地 真衣子":"2001520","安藤 歩":"2001522","宮下 真衣子":"2001530","田中 望帆子":"2001551",
    "河合 萌夏":"2001555","関澤 優":"2001563","高柳 愛理":"2001564","三村 なつみ":"2001565",
    "川崎 真奈美":"2001572","西山 幸広":"2001573","升水 太一":"2001576","八木 ひとみ":"2001584",
    "近藤 優香":"2001579","大村 遥香":"2001585","杉原 康代":"2001586","成田 みどり":"2001668",
    "佐藤 更紗":"2001587","山崎 詠万":"2001589","中田 静里奈":"2001590","諸石 美幸":"2001591",
    "返済管理 チーム":"2001601","督促 部":"2001602","精算 チーム":"2001603",
    "山田 れな":"2001625","阿部 大希":"2001631","北村 霞織":"2001635","横尾 綾奈":"2001636",
    "米倉 理紗":"2001634","半田 暁美":"2001638","山中 輝":"2001642","中野 修作":"2001644",
    "宮窪 七海":"2001650","渡辺 真由":"2001653","石井 紗英":"2001654","鈴木 ひなた":"2001655",
    "高倉 沙也加":"2001656","伊藤 亜加音":"2001657","阿尻 茜":"2001658","今泉 響":"2001660",
    "相川 翔":"2001664","鈴木 亜弥":"2001665","森田 健太":"2001666","小泉 もえこ":"2001667",
    "河合 麻里奈":"2001672","調査 班":"2001183","成田 朱里":"2001673","筒井 実伽里":"2001674",
    "渡邊 理沙":"2001680","小杉 紅葉":"2001678","加地 一晴":"2001679","土信田 ほのか":"2001685",
    "岩佐 彩子":"2001702","上ノ坊 友紀":"2001703","松元 みゆう":"2001704","吉田 冴香":"2001705",
    "山下 修平":"2001192","伊藤 崇":"2001087","和解 班":"2001211","山下 啓臣":"2001088",
    "米良 拓馬":"2001132","中村 美月":"2001208","白垣 充崇":"2001217","池田 祥子":"2001309",
    "松田 佳楠子":"2001335","那須 友明":"2001330","播磨 寿里華":"2001347","経理 班":"2001212",
    "大庭 真理":"2001348","松田 翼":"2001349","村里 祐理":"2001369","山野 雄太郎":"2001401",
    "辻 日菜子":"2001416","近藤 きよら":"2001429","守田 有子":"2001430","八ツ繁 姫乃":"2001467",
    "堂領 美来":"2001469","土屋 要":"2001473","広政 加純":"2001496","進 由菜":"2001527",
    "中村 峻":"2001477","尾田 佳那子":"2001581","遠藤 大陸":"2001588","濱﨑 美衣":"2001659",
    "村上 雄大":"2001810","坂本 悠":"2001836","鶴田 愛菜":"2001868","井上 美有":"2001939",
    "Python 自動登録":"2001875","中西 結香":"2001877","事件登録 チーム":"2001890",
    "原 愛理紗":"2001892","森脇 彩乃":"2001937","入金管理 チーム":"2001923",
    "貞松 玲奈":"2001938","顧客支援 チーム":"2002128",
    "NCS ヘルプ1":"2001497","NCS ヘルプ2":"2001498","NCS ヘルプ3":"2001499",
    "NCS ヘルプ4":"2001500","NCS ヘルプ5":"2001502","NCS ヘルプ6":"2001503",
    "NCS ヘルプ7":"2001951","NCS ヘルプ8":"2001952","NCS ヘルプ9":"2001953","NCS ヘルプ10":"2001954",
}


def strip_counter(text):
    """電話面談(1) → 電話面談  /  提案アポ1(4) → 提案アポ1"""
    return re.sub(r'\(\d+\)$', '', text).strip()


async def scrape_previous(page, cid):
    """履歴ページの最新エントリからフォーム値を取得"""
    await page.goto(
        f'https://mitsuba.leaduplus.pro/debt/consulter/contactHistoryNA/view/{cid}'
    )
    await page.wait_for_load_state('networkidle')

    raw = await page.evaluate("""
        (function() {
            var entry = document.querySelector('.card-body.border-bottom.border-primary');
            if (!entry) return null;
            var result = {};
            entry.querySelectorAll('.col-2').forEach(function(col) {
                var labelEl = col.querySelector('.font-weight-bold');
                var valueEl = col.querySelector('li:not(.font-weight-bold):not([class])');
                if (!valueEl) {
                    // class="" のケースにも対応
                    var lis = col.querySelectorAll('li');
                    lis.forEach(function(li) {
                        if (!li.classList.contains('font-weight-bold')) valueEl = li;
                    });
                }
                if (labelEl && valueEl) {
                    var label = labelEl.textContent.trim();
                    var value = valueEl.textContent.trim();
                    if (label && value) result[label] = value;
                }
            });
            return result;
        })()
    """)

    if not raw:
        return {}

    result = {}

    # 対応者
    name = raw.get('対応者', '').strip()
    if name and name in USER_REVERSE:
        result['user_id'] = USER_REVERSE[name]

    # 対応ステータス
    status_text = raw.get('対応ステータス', '').strip()
    if status_text in REVERSE['mst_contact_status_id']:
        result['mst_contact_status_id'] = REVERSE['mst_contact_status_id'][status_text]

    # 受発信
    direction = raw.get('受発信', '').strip()
    if direction in REVERSE['contact_direction_type']:
        result['contact_direction_type'] = REVERSE['contact_direction_type'][direction]

    # 通信手段
    tool = raw.get('通信手段', '').strip()
    if tool in REVERSE['contact_tool_type']:
        result['contact_tool_type'] = REVERSE['contact_tool_type'][tool]

    # 理由
    reason = raw.get('理由', '').strip()
    if reason in REVERSE['reason']:
        result['reason'] = REVERSE['reason'][reason]

    # NA内容（末尾の(N)カウンターを除去して照合）
    na_text = strip_counter(raw.get('NA内容', '').strip())
    if na_text in REVERSE['mst_consulter_next_action_id']:
        result['mst_consulter_next_action_id'] = REVERSE['mst_consulter_next_action_id'][na_text]

    return result


async def run_automation(config, ids, status):
    use_inherit = config.get('inherit_previous', True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, slow_mo=150)
        page = await browser.new_page()

        try:
            # ── ログイン（最初のIDのページへアクセスしてリダイレクト先でログイン）──
            first_id = str(ids[0]).strip()
            start_url = f'https://mitsuba.leaduplus.pro/debt/consulter/contactHistoryNA/view/{first_id}'
            await page.goto(start_url)
            await page.wait_for_load_state('networkidle')

            # ログインページへリダイレクトされた場合（/debt/login）
            if await page.query_selector('input[name="name"]'):
                login_id = config.get('login_email', '')
                password = config.get('login_password', '')
                if not login_id or not password:
                    status['log'].append('❌ ログインID・パスワードが未設定です')
                    status['running'] = False
                    await browser.close()
                    return

                await page.fill('input[name="name"]', login_id)
                await page.fill('input[name="password"]', password)
                await page.click('button[type="submit"]')
                await page.wait_for_load_state('networkidle')

                # ログイン後もログインフォームが残っていれば失敗
                if await page.query_selector('input[name="name"]'):
                    status['log'].append('❌ ログイン失敗: IDまたはパスワードが違います')
                    status['running'] = False
                    await browser.close()
                    return

                status['log'].append('✓ ログイン成功')

            # ── 各ID処理ループ ──
            for i, cid in enumerate(ids):
                if status.get('stop_requested'):
                    status['log'].append('⏹ ユーザーにより停止されました')
                    break

                cid = str(cid).strip()
                if not cid:
                    continue

                status['current_id'] = cid

                try:
                    now = datetime.now()
                    today = now.strftime('%Y/%m/%d')
                    time_now = now.strftime('%H:%M')

                    # ── 前回値を取得（継承ON の場合）──
                    prev = {}
                    if use_inherit:
                        try:
                            prev = await scrape_previous(page, cid)
                            if prev:
                                status['log'].append(f'  └ {cid}: 前回値を取得しました')
                        except Exception:
                            pass  # 取得失敗しても処理は続行

                    # 設定値優先 / 空欄なら前回値 を使う
                    def val(key):
                        return config.get(key) or prev.get(key, '')

                    # ── 登録フォームへ遷移 ──
                    popup_url = f'https://mitsuba.leaduplus.pro/debt/consulter/contactHistoryNA/popup/1/{cid}'
                    await page.goto(popup_url)
                    await page.wait_for_load_state('networkidle')

                    if await page.query_selector('input[name="name"]'):
                        status['log'].append('❌ セッションが切れました。ツールを再起動してください。')
                        break

                    form = await page.query_selector('form.js-contact-history-na-form')
                    if not form:
                        status['log'].append(f'⚠ {cid}: フォームが見つかりません（IDが存在しない可能性）')
                        status['progress'] = i + 1
                        continue

                    # ── 対応日時（常に実行当日の現在時刻）──
                    await page.evaluate(f"""
                        (function() {{
                            var d = document.querySelector('input[name="contact_date"]');
                            if (d) {{ d.value = '{today}'; d.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                            var t = document.querySelector('input[name="contact_time"]');
                            if (t) {{ t.value = '{time_now}'; t.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                        }})();
                    """)

                    # ── 対応者 ──
                    if val('user_id'):
                        await page.select_option('select[name="user_id"]', val('user_id'))

                    # ── 対応中ステータス ──
                    if val('mst_contact_status_id'):
                        await page.select_option('select[name="mst_contact_status_id"]', val('mst_contact_status_id'))

                    # ── 受発信（ラジオ）──
                    if val('contact_direction_type'):
                        v = val('contact_direction_type')
                        radios = await page.query_selector_all('input[name="contact_direction_type"]')
                        for r in radios:
                            if await r.get_attribute('value') == v:
                                await r.check()
                                break

                    # ── 通信手段 ──
                    if val('contact_tool_type'):
                        await page.select_option('select[name="contact_tool_type"]', val('contact_tool_type'))

                    # ── 理由 ──
                    if val('reason'):
                        await page.select_option('select[name="reason"]', val('reason'))

                    # ── NA日時（configのみ。前回の過去日時は継承しない）──
                    na_date = config.get('next_action_date', '')
                    na_time = config.get('next_action_time', '')
                    if na_date or na_time:
                        await page.evaluate(f"""
                            (function() {{
                                var d = document.querySelector('input[name="next_action_date"]');
                                if (d && '{na_date}') {{ d.value = '{na_date}'; d.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                                var t = document.querySelector('input[name="next_action_time"]');
                                if (t && '{na_time}') {{ t.value = '{na_time}'; t.dispatchEvent(new Event('change', {{bubbles:true}})); }}
                            }})();
                        """)

                    # ── NA内容 ──
                    if val('mst_consulter_next_action_id'):
                        await page.select_option(
                            'select[name="mst_consulter_next_action_id"]',
                            val('mst_consulter_next_action_id')
                        )

                    # ── 不通フラグ ──
                    absent_el = await page.query_selector('input[name="is_absent"]')
                    if absent_el:
                        if config.get('is_absent'):
                            await absent_el.check()
                        else:
                            await absent_el.uncheck()

                    # ── 備考（configのみ。前回の備考は継承しない）──
                    note = config.get('contact_history_note', '')
                    if note:
                        await page.fill('textarea[name="contact_history_note"]', note)

                    # ── 登録 ──
                    await page.click('button[type="submit"]')
                    await page.wait_for_load_state('networkidle')
                    await asyncio.sleep(0.3)

                    status['progress'] = i + 1
                    status['log'].append(f'✓ {cid} 登録完了')

                except Exception as e:
                    status['log'].append(f'❌ {cid} エラー: {str(e)[:100]}')
                    status['progress'] = i + 1

        except Exception as e:
            status['log'].append(f'❌ 致命的なエラー: {str(e)[:150]}')

        finally:
            await browser.close()
            status['running'] = False
            if not status.get('stop_requested') and status['progress'] >= status['total']:
                status['log'].append(f'🎉 全{status["total"]}件の処理が完了しました！')
