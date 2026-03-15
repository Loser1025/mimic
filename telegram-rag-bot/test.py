"""動作確認スクリプト"""
import os
from dotenv import load_dotenv
load_dotenv()

print("=== 設定確認 ===")
token = os.getenv("TELEGRAM_BOT_TOKEN")
gemini_key = os.getenv("GEMINI_API_KEY")
print(f"Telegram Token: {token[:20]}..." if token else "❌ TOKENが未設定")
print(f"Gemini API Key: {gemini_key[:10]}..." if gemini_key else "❌ Gemini Keyが未設定")

print("\n=== ChromaDB確認 ===")
import chromadb
from chromadb.utils import embedding_functions
ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="intfloat/multilingual-e5-small")
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(name="knowledge", embedding_function=ef)
print(f"チャンク数: {collection.count()}")

print("\n=== Gemini API確認 ===")
import google.generativeai as genai
genai.configure(api_key=gemini_key)
model = genai.GenerativeModel("gemini-2.0-flash")
try:
    response = model.generate_content("テストです。「OK」とだけ答えてください。")
    print(f"✅ Gemini応答: {response.text}")
except Exception as e:
    print(f"❌ Geminiエラー: {e}")

print("\n=== Telegram Bot確認 ===")
import asyncio
from telegram import Bot
async def check_bot():
    bot = Bot(token=token)
    me = await bot.get_me()
    print(f"✅ Bot名: @{me.username}")
asyncio.run(check_bot())
