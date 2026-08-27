# Build context is the repository root (see docker-compose.yml: context: ..) so this
# file can copy spike/ and contracts/ from outside workspace_local/ without modifying
# them - workspace_local/ only ever reads them.

# ---- stage 1: build the React frontend ----
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY workspace_local/frontend/package*.json ./
RUN npm install
COPY workspace_local/frontend/ ./
RUN npm run build

# ---- stage 2: python runtime, serves the API and the built frontend ----
FROM python:3.12-slim AS backend

# Native dependencies for docling/paddleocr's OpenCV-based image processing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY spike/ /app/spike/
COPY contracts/ /app/contracts/
COPY workspace_local/backend/ /app/workspace_local/backend/
COPY --from=frontend-build /app/frontend/dist /app/workspace_local/frontend/dist

RUN pip install --no-cache-dir "/app/spike[docling,paddle,retrieval,reranking]" \
    && pip install --no-cache-dir -r /app/workspace_local/backend/requirements.txt

WORKDIR /app/workspace_local/backend
EXPOSE 8000
# Exactly one worker: settings/upload/job state lives in process memory
# (see app/settings_store.py, app/upload_store.py, app/job_store.py).
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
