# Build context is the REPO ROOT.
# Build:  docker build -f backend/Dockerfile .
#
# Weights are trained locally and committed to data/weights/.

# ---- stage 1: install dependencies -----------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- stage 2: runtime -------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /install /usr/local
COPY backend/app          ./app
COPY data/dataset.csv     ./data/dataset.csv
COPY data/weights         ./data/weights

ENV DATASET_PATH=/app/data/dataset.csv \
    WEIGHTS_DIR=/app/data/weights

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
