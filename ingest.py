"""
RAG Ingestion Script
Reads all markdown files from data/RAG, embeds them using Google's
text-embedding-004 model, and stores them in a local ChromaDB collection.

Run this script once (and re-run whenever the RAG data changes):
    python ingest.py
"""

import os
import glob
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv
from sqlmodel import Session
from sqlalchemy import text
from database import engine
from models import RAGKnowledge

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
RAG_DATA_DIR    = os.path.join(os.path.dirname(__file__), "data", "RAG")
COLLECTION_NAME = "rag_knowledge"
EMBEDDING_MODEL = "models/gemini-embedding-001"

# ── Google Generative AI (new SDK) ───────────────────────────────────────────
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY is not set in your .env file.")

client = genai.Client(api_key=GOOGLE_API_KEY)


def embed_text(text: str, retries=5) -> list[float]:
    """Embed a single text using Google's text-embedding-004, with retry logic."""
    for attempt in range(retries):
        try:
            response = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=text,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            time.sleep(1) # Delay to prevent hitting rate limits
            return response.embeddings[0].values
        except Exception as e:
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                print(f"      [!] API Error: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e


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
    print(f"\nFound {len(docs)} markdown files - embedding...\n")

    with Session(engine) as session:
        # Clear existing knowledge base
        session.execute(text("TRUNCATE TABLE ragknowledge CASCADE"))
        session.commit()
        print("Cleared existing database collection")

        for i, doc in enumerate(docs, 1):
            print(f"  [{i:2}/{len(docs)}] {doc['metadata']['source']}")
            embedding = embed_text(doc["content"])

            db_item = RAGKnowledge(
                id=doc["id"],
                content=doc["content"],
                embedding=embedding,
                source=doc["metadata"]["source"],
                category=doc["metadata"]["category"],
                filename=doc["metadata"]["filename"]
            )
            session.add(db_item)
        
        session.commit()

    print(f"\nDone! {len(docs)} documents indexed into Neon pgvector")


if __name__ == "__main__":
    ingest()
