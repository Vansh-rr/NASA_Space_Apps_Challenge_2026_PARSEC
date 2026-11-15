FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PARSEC_DB_PATH=/app/data/fires.duckdb \
    PARSEC_PREVIEW_DIR=/app/model_preview/bc-july-2023 \
    PARSEC_DEMO=0 \
    PARSEC_CORS_ORIGINS=""

WORKDIR /app
COPY requirements-api.txt requirements-tested.txt ./
RUN python -m pip install --no-cache-dir -r requirements-api.txt -c requirements-tested.txt \
    && useradd --create-home --uid 10001 app

COPY phase1_*.py ./
COPY phase2/__init__.py phase2/phase2_config.py phase2/model_preview.py ./phase2/
COPY phase3/ ./phase3/
COPY configs/phase2.yaml ./configs/phase2.yaml
COPY --chown=app:app model_preview/ ./model_preview/
COPY --chown=app:app data/fires.duckdb ./data/fires.duckdb

USER app
EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn phase3.api:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1"]
