"""
File Upload Router
==================
Handles large file uploads (100 MB limit), text extraction, and per-file Q&A.

How it works end-to-end:
  1. Client POSTs a file to /upload/file
  2. The file is saved to disk under /uploads/{user_id}/
  3. Text is extracted (PDF pages, DOCX paragraphs, plain text, etc.)
  4. The extracted text + file metadata is stored in the DB
  5. Client POSTs to /upload/analyze with the file_id and a question
  6. We pass the extracted text to Claude as context and return the answer

Endpoints:
  POST   /upload/file                → Upload a file (≤100 MB)
  GET    /upload/files               → List your uploaded files
  POST   /upload/analyze             → Ask Claude a question about a file
  DELETE /upload/files/{id}          → Delete a file
"""

import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import UploadedFile, User, get_db, Conversation, Message
from schemas import FileUploadResponse, FileAnalyzeRequest, ChatResponse, MessageResponse
from services.file_service import extract_text, get_mime_type, is_supported
from services.claude_service import analyze_file_with_claude

router = APIRouter()

UPLOAD_DIR   = Path("uploads")
MAX_FILE_SIZE = 100 * 1024 * 1024   # 100 MB in bytes


# ─────────────────────────────────────────────────────────────────────────────
# POST /upload/file
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/file",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file (PDF, DOCX, TXT, image — up to 100 MB)",
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload any supported file. The server extracts readable text immediately
    after upload, stores it in the database, and returns a `file_id` you can
    use with the `/upload/analyze` endpoint.

    **Supported formats:** PDF, DOCX, TXT, MD, CSV, JPEG, PNG, GIF, WEBP

    **Size limit:** 100 MB. Files larger than this will be rejected.
    """

    if not is_supported(file.filename):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"File type not supported: '{file.filename}'. "
                "Accepted: PDF, DOCX, TXT, MD, CSV, JPEG, PNG, GIF, WEBP."
            ),
        )

    # ── Read the file into memory (enforce size limit) ────────────────────────
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File is too large ({len(content) / 1e6:.1f} MB). Limit is 100 MB.",
        )

    # ── Save to disk under uploads/{user_id}/ ────────────────────────────────
    user_dir = UPLOAD_DIR / current_user.id
    user_dir.mkdir(parents=True, exist_ok=True)

    safe_name    = f"{uuid.uuid4()}_{Path(file.filename).name}"
    storage_path = user_dir / safe_name

    with open(storage_path, "wb") as f:
        f.write(content)

    # ── Extract text from the file ────────────────────────────────────────────
    extracted_text, mime_type = extract_text(str(storage_path), file.filename)

    # ── Persist file metadata to DB ───────────────────────────────────────────
    db_file = UploadedFile(
        user_id=current_user.id,
        filename=file.filename,
        file_type=mime_type,
        file_size=len(content),
        storage_path=str(storage_path),
        extracted_text=extracted_text,
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    # Return a short preview so the client can confirm extraction worked
    preview = None
    if extracted_text and not extracted_text.startswith("["):
        preview = extracted_text[:300] + ("…" if len(extracted_text) > 300 else "")

    return FileUploadResponse(
        file_id=db_file.id,
        filename=file.filename,
        file_type=mime_type,
        file_size_kb=round(len(content) / 1024, 2),
        extracted_text_preview=preview,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /upload/files
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/files",
    summary="List all files you have uploaded",
)
def list_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns a list of all files uploaded by the authenticated user."""
    files = (
        db.query(UploadedFile)
        .filter(UploadedFile.user_id == current_user.id)
        .order_by(UploadedFile.created_at.desc())
        .all()
    )
    return [
        {
            "file_id":    f.id,
            "filename":   f.filename,
            "file_type":  f.file_type,
            "size_kb":    round((f.file_size or 0) / 1024, 2),
            "created_at": f.created_at,
            "has_text":   bool(f.extracted_text),
        }
        for f in files
    ]


# ─────────────────────────────────────────────────────────────────────────────
# POST /upload/analyze
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/analyze",
    response_model=ChatResponse,
    summary="Ask Claude a question about an uploaded file",
)
def analyze_file(
    payload: FileAnalyzeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ask Claude a question about any file you have previously uploaded.

    The server passes the **full extracted text** of the file to Claude as
    context, so Claude can reason over the entire document — not just a snippet.

    If a `conversation_id` is provided, the answer is stored in that conversation
    so the exchange becomes part of your chat history.
    """

    # ── Fetch the file record ─────────────────────────────────────────────────
    db_file = (
        db.query(UploadedFile)
        .filter(
            UploadedFile.id == payload.file_id,
            UploadedFile.user_id == current_user.id,
        )
        .first()
    )
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found.")

    if not db_file.extracted_text:
        raise HTTPException(
            status_code=422,
            detail="This file has no extractable text. Try uploading a different format.",
        )

    # ── Resolve / create a conversation to store the exchange ────────────────
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
        convo = Conversation(
            user_id=current_user.id,
            title=f"Analysis: {db_file.filename[:60]}",
        )
        db.add(convo)
        db.flush()

    # Load existing history for this conversation
    prior = (
        db.query(Message)
        .filter(Message.conversation_id == convo.id)
        .order_by(Message.created_at)
        .all()
    )
    history = [{"role": m.role, "content": m.content} for m in prior]

    # ── Call Claude ───────────────────────────────────────────────────────────
    try:
        answer, usage = analyze_file_with_claude(
            file_content=db_file.extracted_text,
            question=payload.question,
            file_name=db_file.filename,
            history=history,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {str(e)}")

    # ── Store both turns ──────────────────────────────────────────────────────
    user_msg = Message(conversation_id=convo.id, role="user",
                       content=f"[About file: {db_file.filename}]\n{payload.question}")
    assistant_msg = Message(conversation_id=convo.id, role="assistant", content=answer)
    db.add_all([user_msg, assistant_msg])
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
# DELETE /upload/files/{id}
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an uploaded file",
)
def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deletes a file from disk and removes its database record."""
    db_file = (
        db.query(UploadedFile)
        .filter(UploadedFile.id == file_id, UploadedFile.user_id == current_user.id)
        .first()
    )
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found.")

    # Remove from disk
    if os.path.exists(db_file.storage_path):
        os.remove(db_file.storage_path)

    db.delete(db_file)
    db.commit()
