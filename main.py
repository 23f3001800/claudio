"""
Claude AI Assistant - FastAPI Application
==========================================
A production-ready AI assistant backend powered by Anthropic's Claude API.
Features: Auth, Chat w/ history, File uploads (50MB+), Web search.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from database import init_db
from routers import auth_router, chat_router, upload_router, search_router


# ── Lifespan: runs once at startup and shutdown ───────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    init_db()
    os.makedirs("uploads", exist_ok=True)
    print("✅ Database initialized")
    print("✅ Upload directory ready")
    yield
    print("👋 Shutting down...")


# ── App Configuration ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Claude AI Assistant",
    description="""
    ## Personal AI Assistant powered by Claude

    ### Features
    - 🔐 JWT Authentication (register / login)
    - 💬 Multi-turn Chat with persistent conversation history
    - 📂 File & PDF Upload (up to 100 MB)
    - 🔍 Web Search integration via Claude's native tool
    - 🧠 Per-conversation memory

    ### Getting Started
    1. Register at `/auth/register`
    2. Login at `/auth/login` to get your JWT token
    3. Use the token as `Bearer <token>` in the `Authorization` header
    4. Start chatting at `/chat/message`
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS — adjust origins for production ─────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Restrict this to your frontend domain in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router,   prefix="/auth",   tags=["Authentication"])
app.include_router(chat_router.router,   prefix="/chat",   tags=["Chat"])
app.include_router(upload_router.router, prefix="/upload", tags=["Files"])
app.include_router(search_router.router, prefix="/search", tags=["Web Search"])


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "app": "Claude AI Assistant",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}
