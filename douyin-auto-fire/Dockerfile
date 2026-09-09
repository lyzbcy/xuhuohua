FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/unmev/douyin-auto-fire"
LABEL org.opencontainers.image.description="Douyin automatic streak message sender"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    HEADLESS=true \
    TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt ./

RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt \
    && python -m playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends cron tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/artifacts /data

ENTRYPOINT ["/app/docker/entrypoint.sh"]
