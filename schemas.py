"""
Pydantic Schemas
================
Defines the shape of all request bodies and response payloads.
FastAPI uses these for automatic validation, serialization, and OpenAPI docs.
"""

from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, examples=["john_doe"])
    email: EmailStr = Field(..., examples=["john@example.com"])
    password: str = Field(..., min_length=8, examples=["strongpass123"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int   # seconds


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Conversations ─────────────────────────────────────────────────────────────

class ConversationCreate(BaseModel):
    title: str = Field(default="New Conversation", max_length=200)


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32_000,
                         description="The user's message to Claude")
    conversation_id: Optional[str] = Field(
        default=None,
        description="ID of an existing conversation. Leave null to auto-create a new one."
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="Optional custom system prompt to override the default assistant behavior."
    )
    enable_web_search: bool = Field(
        default=False,
        description="Set to true to let Claude search the web while answering."
    )
    max_tokens: int = Field(default=2048, ge=64, le=8192)


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    conversation_id: str
    message: MessageResponse
    usage: Optional[dict] = None   # token counts returned by Claude


# ── File Upload ───────────────────────────────────────────────────────────────

class FileUploadResponse(BaseModel):
    file_id: str
    filename: str
    file_type: str
    file_size_kb: float
    extracted_text_preview: Optional[str] = None   # first 300 chars of extracted text
    message: str = "File uploaded successfully"


class FileAnalyzeRequest(BaseModel):
    file_id: str = Field(..., description="ID returned from the upload endpoint")
    question: str = Field(..., min_length=1, description="What to ask about the file")
    conversation_id: Optional[str] = None


# ── Search ────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    conversation_id: Optional[str] = None
    max_tokens: int = Field(default=2048, ge=64, le=8192)


class SearchResponse(BaseModel):
    conversation_id: str
    query: str
    answer: str
    usage: Optional[dict] = None
