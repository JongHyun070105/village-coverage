FROM python:3.12-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.7
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
COPY scripts ./scripts
COPY data/demo.json ./data/demo.json
COPY artifacts/data_quality_report.json artifacts/public_schema_manifest.json ./artifacts/

EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
