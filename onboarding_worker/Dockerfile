# onboarding_worker/Dockerfile
# Author: Adam ChapChap Ng'uni — Created: 2025-08-09
# Celery worker container for async Odoo provisioning tasks

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY . /app

CMD ["celery", "-A", "tasks", "worker", "--loglevel=info"]
