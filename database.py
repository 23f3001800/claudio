"""
Database Layer
==============
Uses SQLite via SQLAlchemy for simplicity and portability.
Stores users, conversations, and messages.

To switch to PostgreSQL for production, just change DATABASE_URL to:
  postgresql://user:password@host:5432/dbname
and add `psycopg2-binary` to requirements.txt
"""

from sqlalchemy import (
    create_engine, Column, String, Text, DateTime,
    Integer, ForeignKey, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone
import uuid
import os

# ── Database URL ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./claude_assistant.db")

# connect_args is SQLite-specific; remove for PostgreSQL
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── ORM Models ────────────────────────────────────────────────────────────────

class User(Base):
    """Registered users. Passwords are stored as bcrypt hashes."""
    __tablename__ = "users"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username     = Column(String(50), unique=True, nullable=False, index=True)
    email        = Column(String(120), unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversations = relationship("Conversation", back_populates="user", cascade="all, delete")


class Conversation(Base):
    """A named chat session belonging to a user."""
    __tablename__ = "conversations"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    title      = Column(String(200), default="New Conversation")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user     = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation",
                            cascade="all, delete", order_by="Message.created_at")


class Message(Base):
    """
    A single turn in a conversation.
    role is either 'user' or 'assistant' — matching Claude's API format.
    """
    __tablename__ = "messages"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    role            = Column(String(10), nullable=False)   # 'user' | 'assistant'
    content         = Column(Text, nullable=False)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")


class UploadedFile(Base):
    """Tracks files uploaded by users for reference in chat."""
    __tablename__ = "uploaded_files"

    id              = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id         = Column(String, ForeignKey("users.id"), nullable=False)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=True)
    filename        = Column(String(255), nullable=False)
    file_type       = Column(String(50))
    file_size       = Column(Integer)   # bytes
    storage_path    = Column(String(500), nullable=False)
    extracted_text  = Column(Text)      # pre-extracted text for PDFs/docs
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def init_db():
    """Create all tables. Safe to call multiple times (CREATE IF NOT EXISTS)."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """
    FastAPI dependency that yields a database session.
    Automatically closes the session after the request finishes.
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
