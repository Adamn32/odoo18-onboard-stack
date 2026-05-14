# onboarding_web/app/Dockerfile
# Author: Adam ChapChap Ng'uni — Created: 2025-08-09
# FastAPI + Uvicorn container for the onboarding app

FROM python:3.12-slim

# --- Python & pip behavior ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# --- System deps ---
# psycopg2-binary ships pre-built wheels; no build-essential needed
RUN apt-get update && apt-get install -y --fix-missing --no-install-recommends \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Workdir for the app
WORKDIR /app

# --- Python deps ---
# Expect requirements.txt to be inside onboarding_web/app/
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# --- App code ---
# Because build context is onboarding_web/app, we copy the WHOLE folder
# This must include: main.py, templates/, static/ (with sslogo.png)
COPY . /app

# --- Runtime config ---
EXPOSE 8000

# Optional toggles via env
ENV UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000 \
    UVICORN_RELOAD=0

# Use --reload only in dev (set UVICORN_RELOAD=1 in compose if you want hot reload)
CMD ["sh", "-lc", "uvicorn main:app --host ${UVICORN_HOST} --port ${UVICORN_PORT} $( [ \"$UVICORN_RELOAD\" = \"1\" ] && echo --reload )"]
