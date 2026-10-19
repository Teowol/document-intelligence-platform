# Production image for the document intelligence platform (Phase 10).
# Multi-stage: build wheels first (cached), slim runtime second.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmagic1 libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# platform markers (magic vs magic-bin) resolve correctly on linux/amd64.
RUN pip wheel --no-cache-dir -w /wheels -r requirements.txt

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 libpq5 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*

COPY . .

# Pre-create volume mount points and make runtime dirs writable for the
# unprivileged appuser (fresh named volumes inherit the owner via copy-up).
RUN mkdir -p /app/src/staticfiles /app/src/media && \
    chown -R appuser:appuser /app/src

USER appuser

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
