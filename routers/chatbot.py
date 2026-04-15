"""
Chatbot Router (RAG + Persistent History)

POST /chatbot/sessions              — create a new chat session
GET  /chatbot/sessions              — list all sessions for the current user
GET  /chatbot/sessions/{id}/messages — get all messages in a session
POST /chatbot/sessions/{id}/chat    — send a message (stored + Gemini reply stored)
POST /chatbot/sessions/{id}/stream  — streaming variant (SSE)

All endpoints require a valid JWT (Bearer token).
"""

import os
import json as json_lib
import chromadb
from datetime import datetime, timezone
from typing import Literal

from google import genai
from google.genai import types
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import get_session
from models import User, ChatSession, ChatMessage
from routers.users import get_current_user

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
CHROMA_PATH     = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
COLLECTION_NAME = "rag_knowledge"
EMBEDDING_MODEL = "models/gemini-embedding-001"
CHAT_MODEL      = "gemini-2.5-flash-lite"
TOP_K           = 5

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY is not set in your .env file.")

genai_client = genai.Client(api_key=GOOGLE_API_KEY)

# ── ChromaDB (lazy-loaded) ────────────────────────────────────────────────────
_chroma_client = None
_collection    = None

def get_collection():
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = _chroma_client.get_collection(COLLECTION_NAME)
    return _collection

# ── Schemas ───────────────────────────────────────────────────────────────────
class ChatMessageSchema(BaseModel):
    role: Literal["user", "model"]
    text: str

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: int

class SessionCreate(BaseModel):
    title: str = "New Chat"

class SessionResponse(BaseModel):
    id: int
    title: str
    createdAt: datetime

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: int
    role: str
    text: str
    sources: list[str] | None
    createdAt: datetime

    class Config:
        from_attributes = True

# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/chatbot", tags=["Chatbot"])

# ── Helpers ───────────────────────────────────────────────────────────────────
def embed_query(text: str) -> list[float]:
    response = genai_client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return response.embeddings[0].values

def retrieve(query: str) -> tuple[str, list[str]]:
    """Return (context_block, list_of_source_labels)."""
    collection = get_collection()
    query_embedding = embed_query(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=TOP_K,
        include=["documents", "metadatas"],
    )
    docs    = results["documents"][0]
    metas   = results["metadatas"][0]
    sources = [m["source"] for m in metas]
    context = "\n\n---\n\n".join(docs)
    return context, sources

def build_history(db_messages: list[ChatMessage]) -> list[types.Content]:
    """Convert stored messages to the Gemini history format."""
    valid_roles = {"user", "model"}
    return [
        types.Content(role=msg.role, parts=[types.Part(text=msg.text)])
        for msg in db_messages
        if msg.role in valid_roles
    ]

SYSTEM_PROMPT = """You are a helpful and knowledgeable assistant specializing in automotive vehicles and consumer electronics.
Answer the user's question based ONLY on the context provided below.
If the context does not contain enough information to answer, say so honestly.
Be concise, factual, and friendly.

CONTEXT:
{context}
"""

# ── Session endpoints ─────────────────────────────────────────────────────────
@router.post("/sessions", response_model=SessionResponse)
def create_session(
    body: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    session = ChatSession(user_id=current_user.id, title=body.title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session

@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    sessions = db.exec(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.createdAt.desc())
    ).all()
    return sessions

@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
def get_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.createdAt)
    ).all()

    result = []
    for msg in messages:
        result.append(MessageResponse(
            id=msg.id,
            role=msg.role,
            text=msg.text,
            sources=json_lib.loads(msg.sources) if msg.sources else None,
            createdAt=msg.createdAt,
        ))
    return result

@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    session = db.get(ChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = db.exec(select(ChatMessage).where(ChatMessage.session_id == session_id)).all()
    for msg in messages:
        db.delete(msg)

    db.delete(session)
    db.commit()
    return {"message": "Session deleted"}

# ── Chat endpoints ────────────────────────────────────────────────────────────
@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
async def chat(
    session_id: int,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    chat_session = db.get(ChatSession, session_id)
    if not chat_session or chat_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        context, sources = retrieve(req.message)
        db_messages = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.createdAt)
        ).all()
        history = build_history(db_messages)
        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            text=req.message,
        )
        db.add(user_msg)
        if not db_messages:
            chat_session.title = req.message[:60]
            chat_session.updatedAt = datetime.now(timezone.utc)
            db.add(chat_session)

        response = genai_client.models.generate_content(
            model=CHAT_MODEL,
            contents=history + [
                types.Content(role="user", parts=[types.Part(text=req.message)])
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(context=context),
            ),
        )

        answer = response.text

        model_msg = ChatMessage(
            session_id=session_id,
            role="model",
            text=answer,
            sources=json_lib.dumps(sources),
        )
        db.add(model_msg)
        db.commit()

        return ChatResponse(answer=answer, sources=sources, session_id=session_id)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sessions/{session_id}/stream")
async def chat_stream(
    session_id: int,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    """
    Streaming variant — returns Server-Sent Events (SSE).
      {'type': 'sources', 'sources': [...]}
      {'type': 'chunk',   'text': '...'}
      {'type': 'done'}
      {'type': 'error',   'message': '...'}
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    chat_session = db.get(ChatSession, session_id)
    if not chat_session or chat_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        context, sources = retrieve(req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    db_messages = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.createdAt)
    ).all()
    history = build_history(db_messages)
    user_msg = ChatMessage(session_id=session_id, role="user", text=req.message)
    db.add(user_msg)

    if not db_messages:
        chat_session.title = req.message[:60]
        chat_session.updatedAt = datetime.now(timezone.utc)
        db.add(chat_session)

    db.commit()

    def generate():
        yield f"data: {json_lib.dumps({'type': 'sources', 'sources': sources})}\n\n"

        full_answer = []
        try:
            for chunk in genai_client.models.generate_content_stream(
                model=CHAT_MODEL,
                contents=history + [
                    types.Content(role="user", parts=[types.Part(text=req.message)])
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT.format(context=context),
                ),
            ):
                if chunk.text:
                    full_answer.append(chunk.text)
                    yield f"data: {json_lib.dumps({'type': 'chunk', 'text': chunk.text})}\n\n"

        except Exception as e:
            yield f"data: {json_lib.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return
        model_msg = ChatMessage(
            session_id=session_id,
            role="model",
            text="".join(full_answer),
            sources=json_lib.dumps(sources),
        )
        db.add(model_msg)
        db.commit()

        yield f"data: {json_lib.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
