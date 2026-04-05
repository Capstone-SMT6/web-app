"""
RAG Ingestion Script
Reads all markdown files from data/RAG, embeds them using Google's
text-embedding-004 model, and stores them in a local ChromaDB collection.

Run this script once (and re-run whenever the RAG data changes):
    python ingest.py
"""

import os
import glob
import chromadb
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
RAG_DATA_DIR    = os.path.join(os.path.dirname(__file__), "data", "RAG")
CHROMA_PATH     = os.path.join(os.path.dirname(__file__), "chroma_db")
COLLECTION_NAME = "rag_knowledge"
EMBEDDING_MODEL = "models/gemini-embedding-001"

# ── Google Generative AI (new SDK) ───────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY is not set in your .env file.")

client = genai.Client(api_key=GOOGLE_API_KEY)

# ── ChromaDB (persistent local storage) ──────────────────────────────────────
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

try:
    chroma_client.delete_collection(COLLECTION_NAME)
    print(f"🗑️  Deleted existing collection '{COLLECTION_NAME}'")
except Exception:
    pass

collection = chroma_client.create_collection(COLLECTION_NAME)
print(f"✅ Created collection '{COLLECTION_NAME}'")


def embed_text(text: str) -> list[float]:
    """Embed a single text using Google's text-embedding-004."""
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return response.embeddings[0].values


def load_markdown_files() -> list[dict]:
    """Recursively find and read all .md files under RAG_DATA_DIR."""
    pattern = os.path.join(RAG_DATA_DIR, "**", "*.md")
    files = glob.glob(pattern, recursive=True)

    documents = []
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        rel_path = os.path.relpath(path, RAG_DATA_DIR)
        source = rel_path.replace("\\", "/")

        parts = rel_path.split(os.sep)
        category = parts[0] if len(parts) > 1 else "general"

        documents.append({
            "id": source,
            "content": content,
            "metadata": {
                "source": source,
                "category": category,
                "filename": os.path.basename(path),
            },
        })

    return documents


def ingest():
    docs = load_markdown_files()
    print(f"\n📂 Found {len(docs)} markdown files — embedding…\n")

    ids, embeddings, contents, metas = [], [], [], []

    for i, doc in enumerate(docs, 1):
        print(f"  [{i:2}/{len(docs)}] {doc['metadata']['source']}")
        embedding = embed_text(doc["content"])

        ids.append(doc["id"])
        embeddings.append(embedding)
        contents.append(doc["content"])
        metas.append(doc["metadata"])

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=contents,
        metadatas=metas,
    )

    print(f"\n🎉 Done! {len(docs)} documents indexed into ChromaDB at '{CHROMA_PATH}'")


if __name__ == "__main__":
    ingest()
