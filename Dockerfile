# Smart Class API (FastAPI) - production image.
#
# Build:  docker build -t smart-class-api .
# Run:    docker run -p 8000:8000 \
#           -e DATABASE_URL=postgresql+psycopg2://user:password@db-host:5432/smart_classroom \
#           -e JWT_SECRET_KEY=<long random value> \
#           -e ADMIN_REGISTRATION_CODE=<code> \
#           -e CORS_ORIGINS=https://your-web-app.example \
#           smart-class-api
#
# Secrets are passed as environment variables only (never baked into the
# image; .env is excluded by .dockerignore).

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)"

# Bring the database schema up to date, then serve.
# One worker on purpose: live-class rooms (WebRTC signaling, whiteboard) are
# kept in memory, so every participant of a class must reach the same process.
# No --reload in production.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
