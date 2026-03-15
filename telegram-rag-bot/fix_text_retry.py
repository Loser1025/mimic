"""レート制限でスキップされた3ファイルをGroqで再処理する"""
import os
import re
import time
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

INPUT_FILE = "./db_contents.txt"
OUTPUT_FILE = "./db_contents_fixed.txt"

RETRY_FILES = ["医療痩身_251219.pdf", "田口オンライン資料", "痩身料金表260302①.pdf"]

PROMPT = """以下はPDFから抽出されたテキストです。改行・スペースの乱れを修正して読みやすく整形してください。
ルール：
- 内容（文章・数字・固有名詞）は一切変えない
- 不自然な改行を結合する（文の途中で切れているもの）
- 余分な空白行を削除する
- 箇条書きや表の構造は維持する

テキスト:
"""

# 元ファイルから対象セクションを抽出
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    content = f.read()

sections = re.split(r"(={60}\n📄 .+?\n={60}\n)", content)

# 修正済みファイルを読み込む
with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
    fixed_content = f.read()

print(f"対象ファイル: {RETRY_FILES}")

for i in range(1, len(sections), 2):
    header = sections[i]
    body = sections[i+1] if i+1 < len(sections) else ""

    filename = re.search(r"📄 (.+?)\s+\(", header)
    name = filename.group(1) if filename else ""

    if not any(r in name for r in RETRY_FILES):
        continue

    print(f"処理中: {name} ({len(body)}文字)", end="", flush=True)

    for attempt in range(3):
        try:
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": PROMPT + body}]
            )
            fixed = response.choices[0].message.content

            # 固定ファイル内の対象セクションを置換
            old_section = header + body
            new_section = header + fixed + "\n"
            fixed_content = fixed_content.replace(old_section, new_section)
            print(f" ✅")
            break
        except Exception as e:
            if attempt < 2:
                print(f" ⏳ 再試行({attempt+1}/3)...", end="", flush=True)
                time.sleep(30)
            else:
                print(f" ❌ 失敗: {e}")

    time.sleep(5)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(fixed_content)

print(f"\n✅ 完了: {OUTPUT_FILE}")
