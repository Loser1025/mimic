
import os
import re
import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR = "./chroma_db"
FIXED_FILE = "./db_contents_fixed.txt"
CHUNK_SIZE = 500

def split_text_smartly(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    """句点「。」や改行で区切り、約500文字ずつのチャンクに分割する"""
    # 改行や句点でテキストをバラバラにする（区切り文字を保持するためにキャプチャグループを使用）
    parts = re.split(r"([。\n])", text)
    
    chunks = []
    current_chunk = ""
    
    for i in range(0, len(parts), 2):
        sentence = parts[i]
        delimiter = parts[i+1] if i+1 < len(parts) else ""
        combined = sentence + delimiter
        
        if len(current_chunk) + len(combined) > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = combined
        else:
            current_chunk += combined
            
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
        
    return chunks

def main():
    if not os.path.exists(FIXED_FILE):
        print(f"❌ {FIXED_FILE} が見つかりません")
        return

    with open(FIXED_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # ファイルセクションの分割
    # パターン: =================...\n📄 ファイル名 (Nチャンク)\n=================...
    sections = re.split(r"\n={10,}\n📄\s*(.*?)\s*\(\d+チャンク\)\n={10,}\n", content)
    
    # re.splitは(ファイル名)をリストに挿入するので、[見出し前, ファイル名1, コンテンツ1, ファイル名2, コンテンツ2, ...] となる
    # 最初の要素は「総チャンク数...」などのヘッダーなので飛ばす
    file_data = []
    for i in range(1, len(sections), 2):
        filename = sections[i].strip()
        text_content = sections[i+1].strip()
        file_data.append((filename, text_content))

    print(f"{len(file_data)}件のファイルを解析しました。")

    # 埋め込みモデル
    print("埋め込みモデルを読み込み中...")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="intfloat/multilingual-e5-small"
    )

    # ChromaDB初期化
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    
    # 既存のコレクションを削除
    try:
        client.delete_collection(name="knowledge")
        print("既存の 'knowledge' コレクションを削除しました。")
    except Exception:
        print("'knowledge' コレクションは存在しません。新規作成します。")

    collection = client.create_collection(
        name="knowledge",
        embedding_function=ef
    )

    total_chunks = 0
    for filename, text in file_data:
        print(f"処理中: {filename}")
        
        chunks = split_text_smartly(text)
        print(f"  チャンク数: {len(chunks)}")
        
        if not chunks:
            continue

        collection.add(
            documents=chunks,
            ids=[f"{filename}_{i}" for i in range(len(chunks))],
            metadatas=[{"source": filename, "chunk": i} for i in range(len(chunks))]
        )
        total_chunks += len(chunks)
        print(f"  ✅ 保存完了")

    print(f"\n✅ 全ての処理が完了しました！ 合計チャンク数: {total_chunks}")

if __name__ == "__main__":
    main()
