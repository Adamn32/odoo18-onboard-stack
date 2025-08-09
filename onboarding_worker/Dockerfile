FROM python:3.11-slim
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=120 PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --upgrade pip && pip install --default-timeout=120 -r /app/requirements.txt -i https://pypi.org/simple
COPY . /app
