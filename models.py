from typing import Optional
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    email: str = Field(unique=True, index=True)
    password: Optional[str] = Field(default=None)
    is_admin: bool = Field(default=False)
    authProvider: str = Field(default="local")
    googleId: Optional[str] = Field(default=None, unique=True)
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str = Field(default="New Chat")
    
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updatedAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="chatsession.id", index=True)
    
    role: str = Field(...)
    text: str = Field(...)
    sources: Optional[str] = Field(default=None)
    
    createdAt: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
