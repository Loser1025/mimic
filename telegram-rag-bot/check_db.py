"""
ChromaDBの中身を確認するスクリプト
使い方: python check_db.py
"""
import chromadb
from chromadb.utils import embedding_functions
from collections import defaultdict

CHROMA_DIR = "./chroma_db"

ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-small"
)
client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(name="knowledge", embedding_function=ef)

total = collection.count()
print(f"=== ChromaDB 概要 ===")
print(f"総チャンク数: {total}\n")

if total == 0:
    print("⚠️  データが入っていません。python ingest.py を実行してください。")
    exit()

# ファイルごとのチャンク数を集計
all_data = collection.get(include=["metadatas", "documents"])
file_chunks = defaultdict(list)
for doc, meta in zip(all_data["documents"], all_data["metadatas"]):
    file_chunks[meta["source"]].append((meta["chunk"], doc))

print("=== ファイル別チャンク数 ===")
files = sorted(file_chunks.keys())
for i, filename in enumerate(files, 1):
    print(f"  [{i}] {filename}: {len(file_chunks[filename])}チャンク")

print("\n操作を選んでください:")
print("  1. ファイルの内容をすべて表示")
print("  2. キーワード検索")
print("  3. 終了")

while True:
    choice = input("\n選択 (1/2/3): ").strip()

    if choice == "1":
        print("\nファイル番号を入力（全ファイルはEnter）: ", end="")
        sel = input().strip()
        if sel == "":
            targets = files
        elif sel.isdigit() and 1 <= int(sel) <= len(files):
            targets = [files[int(sel) - 1]]
        else:
            print("無効な番号です")
            continue

        for filename in targets:
            chunks = sorted(file_chunks[filename], key=lambda x: x[0])
            print(f"\n{'='*60}")
            print(f"📄 {filename}  ({len(chunks)}チャンク)")
            print('='*60)
            full_text = "\n".join(text for _, text in chunks)
            print(full_text)

    elif choice == "2":
        query = input("検索キーワード: ").strip()
        if not query:
            continue
        results = collection.query(query_texts=[query], n_results=min(5, total))
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        print(f"\n【検索: {query}】 {len(docs)}件ヒット")
        for i, (doc, meta) in enumerate(zip(docs, metas), 1):
            print(f"\n  [{i}] {meta['source']} (chunk {meta['chunk']})")
            print(f"  {'-'*50}")
            print(f"  {doc}")

    elif choice == "3":
        break
    else:
        print("1, 2, 3 で選んでください")
