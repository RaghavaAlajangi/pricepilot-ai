# Build context is the REPO ROOT.
# Build:  docker build -f backend/Dockerfile .
#
# Three stages:
#   builder  — pip install (cached layer, rebuilt only when requirements change)
#   trainer  — runs train.py once, writes .joblib files to /app/data/weights/
#   runtime  — copies weights from trainer; no Python build tools in final image

# ---- stage 1: install dependencies -----------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app
# Install both backend and training deps in one pass so the trainer stage
# can reuse this layer.
COPY backend/requirements.txt ./backend-requirements.txt
COPY train/requirements.txt   ./train-requirements.txt
RUN pip install --no-cache-dir --prefix=/install \
        -r backend-requirements.txt \
        -r train-requirements.txt

# ---- stage 2: train models --------------------------------------------------
FROM python:3.11-slim AS trainer

WORKDIR /app
COPY --from=builder /install /usr/local
COPY train/train.py  ./train.py
COPY data/dataset.csv ./data/dataset.csv

# Weights land in /app/data/weights/ — same /data dir as the dataset.
# WEIGHTS_DIR is read by train.py at runtime.
ENV DATASET_PATH=/app/data/dataset.csv \
    WEIGHTS_DIR=/app/data/weights

RUN python train.py

# ---- stage 3: runtime -------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /install /usr/local
COPY backend/app     ./app
COPY data/dataset.csv         ./data/dataset.csv
# Bake the trained weights straight into the image — no volume needed.
COPY --from=trainer /app/data/weights ./data/weights

ENV DATASET_PATH=/app/data/dataset.csv \
    WEIGHTS_DIR=/app/data/weights

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
