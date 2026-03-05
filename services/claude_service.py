"""
Gemini AI Service
=================
Replaces the Anthropic Claude client with Google's Gemini API.
All function signatures are IDENTICAL to the original claude_service.py,
so no other file in the project needs to change.

How Gemini handles conversations (important to understand):
  - Gemini uses a "chat session" object that holds history internally,
    but since our app is stateless (each request is independent), we
    recreate the session on every call and seed it with the full history
    from the database. This mirrors exactly what we did with Claude.

  - Gemini separates the system prompt from the chat history. We pass it
    as `system_instruction` when creating the GenerativeModel, not as a
    message in the history array.

  - Gemini uses "model" instead of "assistant" as the role name for AI
    replies. We translate between the two formats below.

Getting your free API key:
  1. Go to https://aistudio.google.com
  2. Click "Get API Key" — no credit card needed
  3. Add it to your .env file as GOOGLE_API_KEY
"""

import google.generativeai as genai
import os
from typing import Optional

# ── Configure the Gemini client with your API key ────────────────────────────
# genai.configure() is a one-time global setup call. It reads the key from
# your environment so you never hardcode secrets in source code.
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Gemini 1.5 Flash is free-tier eligible, fast, and has a 1M token context
# window — perfect for long documents and conversation history.
# Swap to "gemini-1.5-pro" later if you need stronger reasoning (still free
# at low usage, just slower and has tighter rate limits).
MODEL = "gemini-1.5-flash"

DEFAULT_SYSTEM_PROMPT = """You are a helpful, knowledgeable, and friendly personal AI assistant.
You have access to the user's uploaded files and can search the web when needed.
Always respond in a clear and concise manner. If you're unsure about something, say so.
When the user shares a file or document, analyze it carefully before answering questions about it."""


def _translate_history_to_gemini(history: list[dict]) -> list[dict]:
    """
    Convert our internal message format to Gemini's expected format.

    Our internal format (matches Claude / OpenAI convention):
        {"role": "user",      "content": "Hello"}
        {"role": "assistant", "content": "Hi there!"}

    Gemini's expected format:
        {"role": "user",  "parts": ["Hello"]}
        {"role": "model", "parts": ["Hi there!"]}

    The key differences are:
      1. "content" becomes "parts" (a list, because Gemini supports multi-modal parts)
      2. "assistant" role is renamed to "model"
    """
    translated = []
    for msg in history:
        role = "model" if msg["role"] == "assistant" else "user"
        translated.append({"role": role, "parts": [msg["content"]]})
    return translated


def chat_with_claude(
    history: list[dict],
    user_message: str,
    system_prompt: Optional[str] = None,
    enable_web_search: bool = False,
    max_tokens: int = 2048,
    file_context: Optional[str] = None,
) -> tuple[str, dict]:
    """
    Send a message to Gemini and return (reply_text, usage_stats).

    This function has the SAME signature as the original Claude version,
    so all routers (chat, search, upload) call it without any modification.

    Parameters
    ----------
    history          : All previous messages in this conversation (from DB)
    user_message     : The user's current message
    system_prompt    : Optional override for the assistant's persona/behavior
    enable_web_search: Gemini has built-in Google Search grounding — we enable
                       it here when requested (no extra API key needed)
    max_tokens       : Cap on the response length
    file_context     : Extracted text from an uploaded file, prepended to the
                       user message so Gemini can "read" the document
    """

    # ── 1. Prepend file content if a document was provided ───────────────────
    # We wrap the file content in clear markers so Gemini understands that
    # the text between them is document content, not part of the question.
    if file_context:
        full_user_message = (
            f"[FILE CONTENT]\n{file_context}\n[END FILE CONTENT]\n\n"
            f"Using the file content above, please answer:\n{user_message}"
        )
    else:
        full_user_message = user_message

    # ── 2. Configure optional tools ──────────────────────────────────────────
    # Gemini's Google Search grounding is their equivalent of Claude's web
    # search tool. It automatically searches Google when the query needs
    # real-time information. No separate API key required.
    tools = []
    if enable_web_search:
        tools = [{"google_search_retrieval": {}}]

    # ── 3. Build the GenerativeModel with the system prompt ──────────────────
    # In Gemini's API, the system prompt is set at the model level, not as
    # a message in the conversation. This is different from Claude, where
    # system is a separate top-level parameter alongside messages.
    model = genai.GenerativeModel(
        model_name=MODEL,
        system_instruction=system_prompt or DEFAULT_SYSTEM_PROMPT,
        tools=tools if tools else None,
        generation_config=genai.GenerationConfig(max_output_tokens=max_tokens),
    )

    # ── 4. Start a chat session seeded with prior history ────────────────────
    # Gemini's start_chat() takes the full history so the model has context.
    # We translate our internal format (role: assistant) → Gemini's (role: model).
    gemini_history = _translate_history_to_gemini(history)
    chat = model.start_chat(history=gemini_history)

    # ── 5. Send the current message and get the response ─────────────────────
    response = chat.send_message(full_user_message)
    reply_text = response.text

    # ── 6. Extract usage stats if available ──────────────────────────────────
    # Gemini returns token counts in usage_metadata. We return them in the
    # same shape as before so the ChatResponse schema stays compatible.
    usage = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = {
            "input_tokens":  response.usage_metadata.prompt_token_count,
            "output_tokens": response.usage_metadata.candidates_token_count,
        }

    return reply_text, usage


def analyze_file_with_claude(
    file_content: str,
    question: str,
    file_name: str,
    history: list[dict] = None,
    max_tokens: int = 2048,
) -> tuple[str, dict]:
    """
    Specialized wrapper for document Q&A. Injects a document-focused
    system prompt and passes the full file text as context to Gemini.
    The function name is kept as-is so the upload router doesn't need changes.
    """
    return chat_with_claude(
        history=history or [],
        user_message=question,
        system_prompt=(
            f"You are a document analysis assistant. The user has uploaded '{file_name}'. "
            "Read the document content carefully and answer questions about it accurately. "
            "Quote relevant sections when it helps support your answer."
        ),
        file_context=file_content,
        max_tokens=max_tokens,
    )
