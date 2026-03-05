"""
File Processing Service
=======================
Handles text extraction from uploaded files so Claude can "read" them.

Supported formats:
  - PDF        → PyMuPDF (fitz) extracts text page by page
  - DOCX       → python-docx extracts paragraphs
  - TXT / MD   → plain read
  - Images     → converted to base64 for Claude's vision API (not text-extracted)

The extracted text is stored in the `uploaded_files` DB table so we don't have
to re-extract on every question about the same file.
"""

import os
import base64
import mimetypes
from pathlib import Path


# ── Supported MIME types ──────────────────────────────────────────────────────
TEXT_TYPES  = {"text/plain", "text/markdown", "text/csv"}
PDF_TYPE    = "application/pdf"
DOCX_TYPE   = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

MAX_TEXT_CHARS = 150_000   # ~100k tokens — stay safely within Claude's context window


def get_mime_type(filename: str) -> str:
    """Guess the MIME type from the file extension."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def is_supported(filename: str) -> bool:
    """Return True if we know how to handle this file type."""
    mime = get_mime_type(filename)
    return mime in {PDF_TYPE, DOCX_TYPE, *TEXT_TYPES, *IMAGE_TYPES}


def extract_text(file_path: str, filename: str) -> tuple[str | None, str]:
    """
    Extract text from the file at `file_path`.
    Returns (extracted_text_or_None, mime_type).
    Returns None for images (handled separately via base64).
    """
    mime = get_mime_type(filename)

    # ── PDF ──────────────────────────────────────────────────────────────────
    if mime == PDF_TYPE:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            pages = []
            for page_num, page in enumerate(doc, start=1):
                text = page.get_text()
                if text.strip():
                    pages.append(f"--- Page {page_num} ---\n{text}")
            full_text = "\n\n".join(pages)
            return full_text[:MAX_TEXT_CHARS], mime
        except ImportError:
            return "[PyMuPDF not installed — cannot extract PDF text]", mime
        except Exception as e:
            return f"[PDF extraction error: {e}]", mime

    # ── DOCX ─────────────────────────────────────────────────────────────────
    if mime == DOCX_TYPE:
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)[:MAX_TEXT_CHARS], mime
        except ImportError:
            return "[python-docx not installed — cannot extract DOCX text]", mime
        except Exception as e:
            return f"[DOCX extraction error: {e}]", mime

    # ── Plain text / Markdown / CSV ──────────────────────────────────────────
    if mime in TEXT_TYPES:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()[:MAX_TEXT_CHARS], mime
        except Exception as e:
            return f"[Text read error: {e}]", mime

    # ── Images — return None (caller handles vision API) ─────────────────────
    if mime in IMAGE_TYPES:
        return None, mime

    return f"[Unsupported file type: {mime}]", mime


def file_to_base64(file_path: str) -> str:
    """Read a file and return its base64-encoded content (used for images)."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def human_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable string like '12.3 KB' or '4.5 MB'."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
