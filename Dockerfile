# --- frontend
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- app
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=web /web/dist ./frontend/dist
ENV FIDC_DATA_DIR=/data \
    FIDC_STATIC_DIR=/app/frontend/dist \
    PYTHONUNBUFFERED=1
VOLUME /data
WORKDIR /app/backend
EXPOSE 8000
# Na primeira subida a base não existe: o ETL roda em segundo plano (~3 min) e a API já responde.
CMD ["sh", "-c", "[ -f /data/fidc.duckdb ] || (python -m fidc.etl &) ; exec uvicorn fidc.api.main:app --host 0.0.0.0 --port 8000"]
