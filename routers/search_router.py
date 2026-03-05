"""
Web Search Router
=================
Exposes a dedicated endpoint for web-search-powered answers.

Instead of integrating a third-party search API (Tavily, SerpAPI, etc.),
we use Claude's NATIVE web search tool (`web_search_20250305`), which is
built into the Anthropic API. This means:
  - No extra API keys needed
  - Claude decides when and what to search
  - Results are already synthesized into a coherent answer
  - Citations are naturally woven into the response

Endpoints:
  POST /search/query  → Search the web and get a Claude-synthesized answer
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database import get_db, User, Conversation, Message
from auth import get_current_user
from schemas import SearchRequest, SearchResponse
from services.claude_service import chat_with_claude

router = APIRouter()

SEARCH_SYSTEM_PROMPT = """You are a research assistant with access to real-time web search.
When answering a question:
1. Search the web for the most current information.
2. Synthesize what you find into a clear, accurate, well-organized answer.
3. Mention your sources naturally in the response (e.g., "According to Reuters...").
4. If search results are conflicting, acknowledge the discrepancy.
5. Always prioritize recency — prefer sources from the past year unless historical context is needed."""


@router.post(
    "/query",
    response_model=SearchResponse,
    summary="Ask a question with real-time web search",
)
def web_search_query(
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ask Claude a question and let it search the web for up-to-date information.

    Unlike a regular `/chat/message` call (where you opt in with `enable_web_search`),
    this endpoint **always** enables web search. It's designed for research queries
    where current information is essential — news, prices, recent events, etc.

    The answer is stored in a conversation (auto-created if none provided),
    so you can follow up with more questions via `/chat/message`.
    """

    # ── Resolve or create a conversation ─────────────────────────────────────
    if payload.conversation_id:
        convo = (
            db.query(Conversation)
            .filter(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == current_user.id,
            )
            .first()
        )
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    else:
        title = f"Search: {payload.query[:60]}" + ("…" if len(payload.query) > 60 else "")
        convo = Conversation(user_id=current_user.id, title=title)
        db.add(convo)
        db.flush()

    # ── Load existing history ─────────────────────────────────────────────────
    prior = (
        db.query(Message)
        .filter(Message.conversation_id == convo.id)
        .order_by(Message.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in prior]

    # ── Call Claude WITH web search enabled ───────────────────────────────────
    try:
        answer, usage = chat_with_claude(
            history=history,
            user_message=payload.query,
            system_prompt=SEARCH_SYSTEM_PROMPT,
            enable_web_search=True,          # Always on for this endpoint
            max_tokens=payload.max_tokens,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Claude API / search error: {str(e)}",
        )

    # ── Persist both turns ────────────────────────────────────────────────────
    user_msg      = Message(conversation_id=convo.id, role="user",      content=payload.query)
    assistant_msg = Message(conversation_id=convo.id, role="assistant", content=answer)
    db.add_all([user_msg, assistant_msg])
    convo.updated_at = datetime.now(timezone.utc)
    db.commit()

    return SearchResponse(
        conversation_id=convo.id,
        query=payload.query,
        answer=answer,
        usage=usage,
    )
