FROM python:3.12-slim
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=120 PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --upgrade pip && pip install --default-timeout=120 -r /app/requirements.txt -i https://pypi.org/simple && python - <<'PY'
import psycopg2, sqlalchemy; print('psycopg2 + sqlalchemy import OK')
PY
COPY . /app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
