# Dockerfile — AI Exam Proctoring Backend
# Optimised for Render.com free tier (CPU-only, 512 MB RAM)
# Build context: the backend/ directory.

FROM python:3.11-slim

# System libraries (needed by some indirect deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for SQLite persistent disk
RUN mkdir -p /app/data

# Render injects PORT automatically; default 8000 for local dev
ENV PORT=8000
ENV APP_ENV=production

EXPOSE 8000

# Health check so Render knows when the app is ready
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
    CMD curl -f http://localhost:$PORT/health || exit 1

# --workers 1 on free tier (512 MB RAM). Use 2 on paid.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1 --log-level info"]
