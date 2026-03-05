"""
Chat Router
===========
The heart of the application. Handles multi-turn conversations with Claude,
persisting every turn to the database so history is maintained across sessions.

Endpoints:
  POST /chat/message                        → Send a message (creates a new conversation if none given)
  GET  /chat/conversations                  → List all your conversations
  GET  /chat/conversations/{id}/messages    → View full history of a conversation
  DELETE /chat/conversations/{id}           → Delete a conversation
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database import get_db, User, Conversation, Message
from auth import get_current_user
from schemas import (
    ChatRequest, ChatResponse, MessageResponse,
    ConversationCreate, ConversationResponse,
)
from services.claude_service import chat_with_claude

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: fetch a conversation or raise 404
# ─────────────────────────────────────────────────────────────────────────────

def get_conversation_or_404(
    conversation_id: str,
    user_id: str,
    db: Session,
) -> Conversation:
    convo = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return convo


# ─────────────────────────────────────────────────────────────────────────────
# POST /chat/message
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/message",
    response_model=ChatResponse,
    summary="Send a message to Claude",
)
def send_message(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Send a message and receive Claude's reply.

    **How conversation history works:** every prior message in the conversation
    is fetched from the database and sent to Claude on each call. This is the
    standard pattern for LLM statelessness — Claude has no memory of its own,
    so we simulate it by replaying the full history each time.

    If `conversation_id` is omitted, a new conversation is created automatically.
    The first user message is used as the conversation title.

    Set `enable_web_search: true` to let Claude search the web while answering.
    """

    # ── 1. Resolve or create the conversation ────────────────────────────────
    if payload.conversation_id:
        convo = get_conversation_or_404(payload.conversation_id, current_user.id, db)
    else:
        # Auto-create a new conversation titled with the first 80 chars of the message
        title = payload.message[:80] + ("…" if len(payload.message) > 80 else "")
        convo = Conversation(user_id=current_user.id, title=title)
        db.add(convo)
        db.flush()   # assigns convo.id without committing yet

    # ── 2. Load full message history for this conversation ───────────────────
    prior_messages = (
        db.query(Message)
        .filter(Message.conversation_id == convo.id)
        .order_by(Message.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in prior_messages]

    # ── 3. Call Claude ────────────────────────────────────────────────────────
    try:
        reply_text, usage = chat_with_claude(
            history=history,
            user_message=payload.message,
            system_prompt=payload.system_prompt,
            enable_web_search=payload.enable_web_search,
            max_tokens=payload.max_tokens,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Claude API error: {str(e)}",
        )

    # ── 4. Persist both turns to the database ─────────────────────────────────
    user_msg = Message(
        conversation_id=convo.id,
        role="user",
        content=payload.message,
    )
    assistant_msg = Message(
        conversation_id=convo.id,
        role="assistant",
        content=reply_text,
    )
    db.add_all([user_msg, assistant_msg])

    # Update conversation's updated_at timestamp
    convo.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_msg)

    return ChatResponse(
        conversation_id=convo.id,
        message=MessageResponse(
            id=assistant_msg.id,
            role=assistant_msg.role,
            content=assistant_msg.content,
            created_at=assistant_msg.created_at,
        ),
        usage=usage,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /chat/conversations
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/conversations",
    response_model=list[ConversationResponse],
    summary="List all your conversations",
)
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns all conversations for the authenticated user, newest first."""
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /chat/conversations/{id}/messages
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
    summary="Get all messages in a conversation",
)
def get_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the full message history of a conversation in chronological order.
    Useful for rendering a chat UI or reviewing past discussions.
    """
    convo = get_conversation_or_404(conversation_id, current_user.id, db)
    return (
        db.query(Message)
        .filter(Message.conversation_id == convo.id)
        .order_by(Message.created_at)
        .all()
    )


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /chat/conversations/{id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a conversation and all its messages",
)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    convo = get_conversation_or_404(conversation_id, current_user.id, db)
    db.delete(convo)
    db.commit()
