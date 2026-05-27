"""
Telegram RAG Bot
使い方: python bot.py
グループ内でボットをメンションすると回答します
"""

import os
import chromadb
from groq import Groq
import google.generativeai as genai
from chromadb.utils import embedding_functions
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

CHROMA_DIR = "./chroma_db"
TOP_K = 4

SYSTEM_PROMPT = (
    "あなたはグループの資料に基づいて質問に答えるアシスタントです。"
    "提供された資料の内容のみを使って回答してください。"
    "資料に記載がない場合は「資料には記載がありません」と答えてください。"
    "回答は日本語で、簡潔にまとめてください。"
)

# 利用可能なモデル設定
MODELS = {
    "groq-llama":  {"label": "Groq / Llama 3.3 70B",        "provider": "groq",        "model": "llama-3.3-70b-versatile"},
    "groq-llama8": {"label": "Groq / Llama 3.1 8B (高速)",  "provider": "groq",        "model": "llama-3.1-8b-instant"},
    "gemini":      {"label": "Gemini Flash Latest",          "provider": "gemini",      "model": "gemini-flash-latest"},
}
current_model_key = "groq-llama"  # デフォルト
chat_mode = False  # Trueのとき資料を使わず直接モデルと会話

CHAT_SYSTEM_PROMPT = "あなたはMollyです。日本語で回答してください。"

def setup():
    print("埋め込みモデルを読み込み中...")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="intfloat/multilingual-e5-small"
    )
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(name="knowledge", embedding_function=ef)
    print(f"ChromaDB読み込み完了（チャンク数: {collection.count()}）")

    groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    return collection, groq_client

collection, groq_client = setup()

def generate_answer(prompt: str, system_prompt: str = None) -> str:
    """現在選択中のモデルで回答を生成する"""
    model_config = MODELS[current_model_key]
    sys_prompt = system_prompt or SYSTEM_PROMPT

    if model_config["provider"] == "groq":
        response = groq_client.chat.completions.create(
            model=model_config["model"],
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content

    elif model_config["provider"] == "gemini":
        gemini_model = genai.GenerativeModel(
            model_config["model"],
            system_instruction=sys_prompt
        )
        response = gemini_model.generate_content(prompt)
        return response.text


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/model コマンド: モデルの確認・切り替え"""
    global current_model_key

    args = context.args  # コマンドの引数

    if not args:
        # 引数なし → 現在のモデルと一覧を表示
        lines = [f"現在のモデル: *{MODELS[current_model_key]['label']}*\n", "切り替え可能なモデル:"]
        for key, cfg in MODELS.items():
            mark = "✅" if key == current_model_key else "　"
            lines.append(f"{mark} `/model {key}` - {cfg['label']}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    key = args[0].lower()
    if key not in MODELS:
        keys = ", ".join(MODELS.keys())
        await update.message.reply_text(f"❌ 不明なモデルです。使用可能: {keys}")
        return

    current_model_key = key
    print(f"[モデル切替] → {MODELS[key]['label']}")
    await update.message.reply_text(f"✅ モデルを *{MODELS[key]['label']}* に切り替えました", parse_mode="Markdown")

async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/chat コマンド: チャットモードのON/OFF切り替え"""
    global chat_mode
    chat_mode = not chat_mode
    mode_label = MODELS[current_model_key]["label"]
    if chat_mode:
        await update.message.reply_text(
            f"💬 *チャットモード ON*\n資料を使わず {mode_label} と直接会話します。\n`/chat` でRAGモードに戻せます。",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "📄 *RAGモード ON*\n資料に基づいて回答します。",
            parse_mode="Markdown"
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """メッセージを受信して回答する"""
    message = update.message
    if not message or not message.text:
        return

    bot_username = context.bot.username
    is_group = message.chat.type in ["group", "supergroup"]

    if is_group:
        if f"@{bot_username}" not in message.text:
            return
        query = message.text.replace(f"@{bot_username}", "").strip()
    else:
        query = message.text.strip()

    if not query:
        await message.reply_text("質問を入力してください。")
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    # チャットモード: 資料を使わず直接回答
    if chat_mode:
        print(f"[チャット] モデル:{MODELS[current_model_key]['label']} query:{query[:50]}")
        try:
            answer = generate_answer(query, system_prompt=CHAT_SYSTEM_PROMPT)
        except Exception as e:
            await message.reply_text(f"❌ エラーが発生しました: {e}")
            return
        await message.reply_text(f"💬 {answer}")
        return

    # RAGモード: 資料を検索して回答
    results = collection.query(query_texts=[query], n_results=min(TOP_K, collection.count()))
    documents = results["documents"][0] if results["documents"] else []
    sources = [m["source"] for m in results["metadatas"][0]] if results["metadatas"] else []
    print(f"[検索] モデル:{MODELS[current_model_key]['label']} チャンク:{sources}")

    if not documents:
        await message.reply_text("資料が見つかりません。まず `python ingest.py` を実行してください。")
        return

    context_text = "\n\n---\n\n".join(documents)
    unique_sources = list(dict.fromkeys(sources))

    prompt = f"""以下の資料を参考に質問に答えてください。

【資料】
{context_text}

【質問】
{query}"""

    try:
        answer = generate_answer(prompt)
    except Exception as e:
        await message.reply_text(f"❌ エラーが発生しました: {e}")
        return

    source_text = "\n".join(f"・{s}" for s in unique_sources)
    reply = f"{answer}\n\n📄 参照資料:\n{source_text}"
    await message.reply_text(reply)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or "ここに" in token:
        print("❌ .env ファイルに TELEGRAM_BOT_TOKEN を設定してください")
        return

    print("Bot起動中...")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("chat", cmd_chat))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    print("✅ Bot起動完了！ Ctrl+C で停止")
    print(f"   デフォルトモデル: {MODELS[current_model_key]['label']}")
    app.run_polling()

if __name__ == "__main__":
    main()
