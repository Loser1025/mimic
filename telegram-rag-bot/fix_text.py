"""ChromaDBの取り込みテキストをGemini APIで整形する"""
import os
import re
import time
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-flash-latest")

INPUT_FILE = "./db_contents.txt"
OUTPUT_FILE = "./db_contents_fixed.txt"

# ファイルを読み込んでセクション（ファイルごと）に分割
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    content = f.read()

sections = re.split(r"(={60}\n📄 .+?\n={60}\n)", content)

PROMPT = """以下はPDFから抽出されたテキストです。改行・スペースの乱れを修正して読みやすく整形してください。
ルール：
- 内容（文章・数字・固有名詞）は一切変えない
- 不自然な改行を結合する（文の途中で切れているもの）
- 余分な空白行を削除する
- 箇条書きや表の構造は維持する

テキスト:
"""

print(f"セクション数: {len(sections)}")

with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    out.write(sections[0])  # ヘッダー部分（総チャンク数等）

    i = 1
    while i < len(sections):
        header = sections[i] if i < len(sections) else ""
        body = sections[i+1] if i+1 < len(sections) else ""
        i += 2

        if not header:
            continue

        filename = re.search(r"📄 (.+?)\s+\(", header)
        name = filename.group(1) if filename else "?"
        print(f"処理中: {name} ({len(body)}文字)", end="", flush=True)

        try:
            response = model.generate_content(PROMPT + body)
            fixed = response.text
            out.write(header + fixed + "\n")
            print(" ✅")
        except Exception as e:
            print(f" ⚠️ エラー: {e} → そのまま保存")
            out.write(header + body + "\n")

        time.sleep(1.5)  # レート制限対策

print(f"\n✅ 完了: {OUTPUT_FILE}")
