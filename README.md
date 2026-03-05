# 🤖 Claude AI Assistant — FastAPI Backend

A production-ready personal AI assistant API powered by **Anthropic Claude**,
built with FastAPI. Features multi-turn conversations, file uploads up to 100 MB,
real-time web search, and JWT authentication.

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 💬 **Chat** | Multi-turn conversations with persistent memory (stored in SQLite) |
| 📂 **File Upload** | PDFs, DOCX, TXT, images up to 100 MB; Claude reads and answers questions about them |
| 🔍 **Web Search** | Claude's native web search tool — no extra API key needed |
| 🔐 **Auth** | JWT-based registration and login — secure your personal instance |
| 📖 **Auto Docs** | Interactive Swagger UI at `/docs`, ReDoc at `/redoc` |
| 🐳 **Docker** | Production-ready Dockerfile + docker-compose for one-command deployment |
| ☁️ **Cloudflare** | Expose securely to the internet via Cloudflare Tunnel (zero open ports) |

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites

- Python 3.12+
- An Anthropic API key → https://console.anthropic.com

### 2. Clone and install

```bash
git clone <your-repo>
cd fastapi-claude-app

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in:

```env
ANTHROPIC_API_KEY=sk-ant-your-key-here
SECRET_KEY=a-very-long-random-string-at-least-64-chars
```

Generate a strong SECRET_KEY with:
```bash
python -c "import secrets; print(secrets.token_hex(64))"
```

### 4. Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs in your browser. You should see the interactive
API documentation. Register a user and start chatting!

---

## 🐳 Docker Deployment

Docker is the recommended way to run this for personal hosting because it
handles all dependencies, runs as a non-root user, and persists data correctly.

### Build and start

```bash
# Make sure your .env file is configured first
docker compose up -d --build
```

That's it. The app is now running at http://localhost:8000.

```bash
# View live logs
docker compose logs -f

# Stop the app
docker compose down

# Rebuild after code changes
docker compose up -d --build
```

Data (database + uploaded files) is persisted in `./data/` on your host machine,
so it survives container restarts and image rebuilds.

---

## ☁️ Deploying with Cloudflare Tunnel

Cloudflare Tunnel lets you expose your locally-running app to the internet
**without opening any ports on your firewall or router**. Traffic goes through
Cloudflare's network, so your server's IP address is never exposed.

This is perfect for a personal app you want to access from anywhere.

### How it works

```
Your device (phone/browser)
        │
        ▼
  Cloudflare network
        │
  (encrypted tunnel)
        │
        ▼
 cloudflared daemon     ←── running on your server
        │
        ▼
  FastAPI app (port 8000)
```

### Step 1 — Install cloudflared

**Ubuntu / Debian (your server):**
```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
```

**macOS:**
```bash
brew install cloudflare/cloudflare/cloudflared
```

### Step 2 — Authenticate cloudflared

```bash
cloudflared tunnel login
```

This opens a browser window. Log in to your Cloudflare account and authorize
the domain you want to use.

### Step 3 — Create a tunnel

```bash
cloudflared tunnel create claude-assistant
```

Note the tunnel ID printed in the output (looks like a UUID).

### Step 4 — Configure the tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <YOUR_TUNNEL_ID>
credentials-file: /root/.cloudflared/<YOUR_TUNNEL_ID>.json

ingress:
  - hostname: ai.yourdomain.com       # ← change to your subdomain
    service: http://localhost:8000
  - service: http_status:404
```

Replace `ai.yourdomain.com` with any subdomain on a domain you manage in Cloudflare.

### Step 5 — Create a DNS record

```bash
cloudflared tunnel route dns claude-assistant ai.yourdomain.com
```

### Step 6 — Start the tunnel

**For testing:**
```bash
cloudflared tunnel run claude-assistant
```

**Run as a system service (auto-starts on reboot):**
```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

Your app is now live at `https://ai.yourdomain.com`. Cloudflare automatically
provides HTTPS with a valid SSL certificate — no Certbot needed.

---

## 📡 API Reference

### Authentication

All endpoints except `/auth/register` and `/auth/login` require a Bearer token.

```bash
# Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com", "password": "mypassword123"}'

# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "mypassword123"}'
# → Returns: {"access_token": "eyJ...", "token_type": "bearer", "expires_in": 86400}
```

### Chat

```bash
# Send a message (creates a new conversation automatically)
curl -X POST http://localhost:8000/chat/message \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain quantum entanglement simply",
    "enable_web_search": false
  }'

# Continue an existing conversation
curl -X POST http://localhost:8000/chat/message \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Can you give me an analogy for that?",
    "conversation_id": "CONVERSATION_ID_FROM_PREVIOUS_RESPONSE"
  }'

# List all conversations
curl http://localhost:8000/chat/conversations \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### File Upload & Analysis

```bash
# Upload a PDF (up to 100 MB)
curl -X POST http://localhost:8000/upload/file \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/your/document.pdf"
# → Returns: {"file_id": "abc-123", "filename": "document.pdf", ...}

# Ask a question about the uploaded file
curl -X POST http://localhost:8000/upload/analyze \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "abc-123",
    "question": "What are the main conclusions of this document?"
  }'
```

### Web Search

```bash
# Ask a question with real-time web search
curl -X POST http://localhost:8000/search/query \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the latest developments in fusion energy in 2025?"
  }'
```

---

## 🗂️ Project Structure

```
fastapi-claude-app/
├── main.py                  ← FastAPI app entry point, CORS, router registration
├── database.py              ← SQLAlchemy models (User, Conversation, Message, UploadedFile)
├── auth.py                  ← JWT creation/verification, bcrypt hashing, auth dependency
├── schemas.py               ← Pydantic request/response models for validation
│
├── routers/
│   ├── auth_router.py       ← POST /auth/register, POST /auth/login, GET /auth/me
│   ├── chat_router.py       ← POST /chat/message, GET /chat/conversations, DELETE
│   ├── upload_router.py     ← POST /upload/file, POST /upload/analyze, DELETE
│   └── search_router.py     ← POST /search/query (always uses web search)
│
├── services/
│   ├── claude_service.py    ← All Claude API calls, tool configuration
│   └── file_service.py      ← PDF/DOCX/text extraction, base64 encoding
│
├── Dockerfile               ← Multi-stage Docker build
├── docker-compose.yml       ← One-command deployment with persistent volumes
├── requirements.txt         ← Python dependencies
├── .env.example             ← Template for environment variables
└── README.md                ← This file
```

---

## 🔒 Security Notes

- **SECRET_KEY** must be a long random string — never use the example value in production.
- **CORS** is currently set to `allow_origins=["*"]`. In production, change this to your
  specific frontend domain in `main.py`.
- Uploaded files are stored per-user in `uploads/{user_id}/` with randomized filenames
  to prevent path traversal attacks.
- Passwords are hashed with bcrypt (work factor 12) — plaintext passwords are never stored.
- JWT tokens expire after 24 hours by default (configurable via `TOKEN_EXPIRE_MINUTES`).

---

## 📦 Upgrading Claude Model

The model is configured in `services/claude_service.py`:

```python
MODEL = "claude-sonnet-4-20250514"
```

Change this to `claude-opus-4-20250514` for more powerful (but slower and more expensive) responses.

---

## 🛠️ Troubleshooting

**"ANTHROPIC_API_KEY not set"** — Make sure your `.env` file exists and has the key filled in.

**PDF extraction returns blank** — Install PyMuPDF: `pip install PyMuPDF`

**"Token expired"** — Log in again via `/auth/login` to get a fresh token.

**Cloudflare tunnel not connecting** — Check `systemctl status cloudflared` and
make sure the `config.yml` tunnel ID matches the credentials file.
