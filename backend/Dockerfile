# Build context is the REPO ROOT (so the dataset can be baked in for
# database-less deployments like Cloud Run).
# Build:  docker build -f backend/Dockerfile .

# ---- stage 1: install dependencies -----------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- stage 2: runtime -------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /install /usr/local
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY data/dataset.csv ./data/dataset.csv

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# ${PORT} is set by Cloud Run; defaults to 8000 for docker compose
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
