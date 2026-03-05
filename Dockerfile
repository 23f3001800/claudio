# ════════════════════════════════════════════════════════════════════════════
# Dockerfile — Claude AI Assistant
# ════════════════════════════════════════════════════════════════════════════
# Multi-stage build:
#   Stage 1 (builder)  — install Python deps into a virtual environment
#   Stage 2 (runtime)  — copy the venv and app code into a slim final image
#
# This keeps the final image small by not including pip, wheel, gcc, etc.
# ════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed for bcrypt and PyMuPDF C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security (never run production apps as root)
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Runtime system libs only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source code
COPY --chown=appuser:appuser . .

# Create the uploads directory with correct ownership
RUN mkdir -p /app/uploads && chown appuser:appuser /app/uploads

# Switch to non-root user
USER appuser

# Expose the application port
EXPOSE 8000

# Health check — Docker will restart the container if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Start the application
# --workers 2 is a safe default for a personal app; increase for higher load
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2
