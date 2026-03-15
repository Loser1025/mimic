"""ChromaDBの全内容をファイルに出力する"""
import chromadb
from chromadb.utils import embedding_functions
from collections import defaultdict

CHROMA_DIR = "./chroma_db"
OUTPUT_FILE = "./db_contents.txt"

ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="intfloat/multilingual-e5-small"
)
client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(name="knowledge", embedding_function=ef)

total = collection.count()
all_data = collection.get(include=["metadatas", "documents"])

file_chunks = defaultdict(list)
for doc, meta in zip(all_data["documents"], all_data["metadatas"]):
    file_chunks[meta["source"]].append((meta["chunk"], doc))

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(f"総チャンク数: {total}\n")
    f.write(f"ファイル数: {len(file_chunks)}\n\n")

    for filename in sorted(file_chunks.keys()):
        chunks = sorted(file_chunks[filename], key=lambda x: x[0])
        f.write(f"{'='*60}\n")
        f.write(f"📄 {filename}  ({len(chunks)}チャンク)\n")
        f.write(f"{'='*60}\n")
        for _, text in chunks:
            f.write(text + "\n")
        f.write("\n")

print(f"✅ 出力完了: {OUTPUT_FILE}")
print(f"   総チャンク数: {total}、ファイル数: {len(file_chunks)}")
for filename in sorted(file_chunks.keys()):
    print(f"   - {filename}: {len(file_chunks[filename])}チャンク")
