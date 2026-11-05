# ---- Python Forensics Background Worker Daemon Dockerfile ----
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV headless and image manipulation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY services/forensics/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and models
COPY services/forensics/app/ ./app/
COPY models/ ./models/

ENV PYTHONPATH=/app
ENV AI_WEIGHTS_PATH=/app/models/ai_detector_v1.pth
ENV PYTHONUNBUFFERED=1

# Run background worker daemon polling database queue
CMD ["python", "-m", "app.worker"]

