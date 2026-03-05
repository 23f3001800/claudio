"""
Claude API Service
==================
Wraps all Anthropic API interactions in one place so routers stay clean.

Key concepts:
  - All conversations are stateless from Claude's perspective. We rebuild the
    full message history from the database on every request and pass it in.
  - Web search is an optional *tool* that Claude can choose to invoke.
  - File content is injected as a text block preceding the user's question.
"""

import anthropic
import os
from typing import Optional

# ── Anthropic client (reads ANTHROPIC_API_KEY from environment) ───────────────
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODEL = "claude-sonnet-4-20250514"   # Latest Sonnet — smart + fast

DEFAULT_SYSTEM_PROMPT = """You are a helpful, knowledgeable, and friendly personal AI assistant.
You have access to the user's uploaded files and can search the web when needed.
Always respond in a clear and concise manner. If you're unsure about something, say so.
When the user shares a file or document, analyze it carefully before answering questions about it.
Today's date and context will be provided in the conversation."""


def build_tools(enable_web_search: bool) -> list:
    """
    Build the tools list to pass to the API.
    Claude's native web_search tool requires no extra API keys — Anthropic runs it.
    """
    if enable_web_search:
        return [{"type": "web_search_20250305", "name": "web_search"}]
    return []


def chat_with_claude(
    history: list[dict],               # Full message history: [{"role": "user", "content": "..."}]
    user_message: str,
    system_prompt: Optional[str] = None,
    enable_web_search: bool = False,
    max_tokens: int = 2048,
    file_context: Optional[str] = None,  # Pre-extracted text from an uploaded file
) -> tuple[str, dict]:
    """
    Send a message to Claude and return (reply_text, usage_stats).

    The full conversation history is passed on every call because Claude has no
    built-in memory — we simulate persistence by storing and replaying history.

    Parameters
    ----------
    history         : Past messages EXCLUDING the current user_message
    user_message    : The current turn's user input
    system_prompt   : Custom override; falls back to DEFAULT_SYSTEM_PROMPT
    enable_web_search: Whether to give Claude the web search tool
    max_tokens      : Maximum tokens in Claude's reply
    file_context    : Extracted text from an uploaded file to prepend to the prompt
    """

    # If a file was provided, prepend its content so Claude "sees" it
    if file_context:
        full_user_message = (
            f"[FILE CONTENT]\n{file_context}\n[END FILE CONTENT]\n\n"
            f"Using the file content above, please answer:\n{user_message}"
        )
    else:
        full_user_message = user_message

    # Build the full messages array: history + this turn
    messages = history + [{"role": "user", "content": full_user_message}]

    tools = build_tools(enable_web_search)

    # Build the API call kwargs — only include `tools` if we have any
    kwargs = dict(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt or DEFAULT_SYSTEM_PROMPT,
        messages=messages,
    )
    if tools:
        kwargs["tools"] = tools

    response = client.messages.create(**kwargs)

    # Extract plain text from the response content blocks
    # (Some blocks may be tool_use or tool_result when web search is active)
    reply_text = " ".join(
        block.text
        for block in response.content
        if hasattr(block, "text")
    ).strip()

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
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
    Specialized call for file Q&A. Passes the entire file content to Claude
    along with the user's question. Returns (answer, usage_stats).
    """
    return chat_with_claude(
        history=history or [],
        user_message=question,
        system_prompt=(
            f"You are a document analysis assistant. The user has uploaded a file called '{file_name}'. "
            "Carefully read the document content provided and answer questions about it accurately. "
            "Quote relevant sections when helpful."
        ),
        file_context=file_content,
        max_tokens=max_tokens,
    )
