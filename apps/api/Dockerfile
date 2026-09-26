FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=8 pip install --no-cache-dir --index-url "$PIP_INDEX_URL" .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn flowguard_api.application:app --host ${FLOWGUARD_API_HOST:-0.0.0.0} --port ${FLOWGUARD_API_PORT:-8000}"]
