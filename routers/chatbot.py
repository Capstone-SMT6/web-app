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
from datetime import datetime, timezone
from typing import Literal

from google import genai
from google.genai import types
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from dotenv import load_dotenv

from database import get_session, engine
from models import User, ChatSession, ChatMessage, RAGKnowledge, UserFitnessProfile, UserStats, WorkoutSession
from routers.users import get_current_user

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "models/gemini-embedding-001"
CHAT_MODEL      = "gemini-flash-latest"
TOP_K           = 5

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY is not set in your .env file.")

genai_client = genai.Client(api_key=GOOGLE_API_KEY)

# ── Schemas ───────────────────────────────────────────────────────────────────
class ChatMessageSchema(BaseModel):
    role: Literal["user", "model"]
    text: str

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[str]
    session_id: str

class SessionCreate(BaseModel):
    title: str = "New Chat"

class SessionResponse(BaseModel):
    id: str
    title: str
    createdAt: datetime

    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: str
    role: str
    text: str
    sources: list[str] | None
    createdAt: datetime

    class Config:
        from_attributes = True

# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/chatbot", tags=["Chatbot"])

# ── Helpers ───────────────────────────────────────────────────────────────────
async def embed_query(text: str) -> list[float]:
    response = await genai_client.aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    return response.embeddings[0].values

async def retrieve(query: str, db: Session) -> tuple[str, list[str]]:
    """Return (context_block, list_of_source_labels)."""
    query_embedding = await embed_query(query)
    stmt = (
        select(RAGKnowledge)
        .order_by(RAGKnowledge.embedding.cosine_distance(query_embedding))
        .limit(TOP_K)
    )
    results = db.exec(stmt).all()
    docs    = [item.content for item in results]
    sources = [item.source for item in results]
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
SYSTEM_PROMPT = """You are a supportive, motivating, and highly knowledgeable personal home trainer for SmaCoFit. 
Your specialty is home fitness, bodyweight exercises (such as push-ups, sit-ups, squats, and planks), correct posture, form correction, workout consistency, and training motivation.

Answer the user's questions in a friendly, encouraging, and professional tone. Guide them on how to execute exercises with proper form, stay consistent, and maintain their daily streak.

Answer the user's question based ONLY on the context provided below. If the context does not contain enough information to answer, answer based on your general knowledge as a fitness expert, but prioritize the provided context.

CONTEXT:
{context}

USER CONTEXT (About the user):
{user_context}
"""

def _build_user_context(user_id: str, db: Session) -> str:
    profile = db.exec(select(UserFitnessProfile).where(UserFitnessProfile.user_id == user_id)).first()
    stats = db.exec(select(UserStats).where(UserStats.user_id == user_id)).first()
    recent_workouts = db.exec(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .order_by(WorkoutSession.date.desc())
        .limit(3)
    ).all()
    
    parts = []
    if profile:
        parts.append(f"- Age: {profile.age}, Gender: {profile.gender.value if profile.gender else 'N/A'}")
        parts.append(f"- Goal: {profile.goal.value if profile.goal else 'N/A'}, Level: {profile.skillLevel.value if profile.skillLevel else 'N/A'}")
        parts.append(f"- Weight: {profile.weight} kg, Height: {profile.height} cm")
    
    if stats:
        parts.append(f"- Current streak: {stats.currentStreak} days, Longest streak: {stats.longestStreak} days")
        parts.append(f"- Total Push-Ups: {stats.totalPushUps}, Total Sit-Ups: {stats.totalSitUps}")
    if recent_workouts:
        parts.append("- Recent Workouts:")
        for w in recent_workouts:
            parts.append(f"  * {w.date.strftime('%Y-%m-%d')}: {w.duration_seconds}s duration, burned {round(w.calories_burned, 1) if w.calories_burned else 0} kcal")
            
    if not parts:
        return "No user context available."
        
    return "\n".join(parts)

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
    session_id: str,
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
    session_id: str,
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
    session_id: str,
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
        context, sources = await retrieve(req.message, db)
        db_messages = db.exec(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.createdAt.desc())
            .limit(20)
        ).all()
        db_messages = list(reversed(db_messages))
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

        user_ctx = _build_user_context(current_user.id, db)
        response = await genai_client.aio.models.generate_content(
            model=CHAT_MODEL,
            contents=history + [
                types.Content(role="user", parts=[types.Part(text=req.message)])
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT.format(context=context, user_context=user_ctx),
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
    session_id: str,
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
        context, sources = await retrieve(req.message, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    db_messages = db.exec(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.createdAt.desc())
        .limit(20)
    ).all()
    db_messages = list(reversed(db_messages))
    history = build_history(db_messages)
    user_msg = ChatMessage(session_id=session_id, role="user", text=req.message)
    db.add(user_msg)

    if not db_messages:
        chat_session.title = req.message[:60]
        chat_session.updatedAt = datetime.now(timezone.utc)
        db.add(chat_session)

    user_ctx = _build_user_context(current_user.id, db)
    db.commit()

    async def generate():
        yield f"data: {json_lib.dumps({'type': 'sources', 'sources': sources})}\n\n"

        full_answer = []
        try:
            stream_response = await genai_client.aio.models.generate_content_stream(
                model=CHAT_MODEL,
                contents=history + [
                    types.Content(role="user", parts=[types.Part(text=req.message)])
                ],
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT.format(context=context, user_context=user_ctx),
                ),
            )
            async for chunk in stream_response:
                if chunk.text:
                    full_answer.append(chunk.text)
                    yield f"data: {json_lib.dumps({'type': 'chunk', 'text': chunk.text})}\n\n"

        except Exception as e:
            yield f"data: {json_lib.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        try:
            with Session(engine) as gen_db:
                model_msg = ChatMessage(
                    session_id=session_id,
                    role="model",
                    text="".join(full_answer),
                    sources=json_lib.dumps(sources),
                )
                gen_db.add(model_msg)
                gen_db.commit()
        except Exception as e:
            yield f"data: {json_lib.dumps({'type': 'error', 'message': f'Database save error: {str(e)}'})}\n\n"
            return

        yield f"data: {json_lib.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
