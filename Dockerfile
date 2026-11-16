# SmartArchive-X API for a hosted server (Railway or Render). The web interface is deployed on Netlify.
# Mount a persistent volume at /data so documents and accounts survive restarts (docs/deployment.md).
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install -r requirements-api.txt
COPY src ./src
COPY tools/fetch_ocr_models.py ./tools/fetch_ocr_models.py
# Pinned, hash-checked Arabic models (script/Arabic reads Arabic-Indic digits).
RUN python tools/fetch_ocr_models.py && mkdir -p /data
ENV SMARTARCHIVE_STORAGE_DIR=/data/smartarchive \
    SMARTARCHIVE_TESSDATA_DIR=/app/models/tessdata \
    SMARTARCHIVE_OCR_LANGUAGES=script/Arabic+ara \
    SMARTARCHIVE_SECURE_COOKIES=true \
    SMARTARCHIVE_CORS_ORIGINS=https://smartarchive-x-kareem.netlify.app
EXPOSE 10000
CMD ["sh", "-c", "uvicorn smartarchive.api.app:app --app-dir src --host 0.0.0.0 --port ${PORT:-10000}"]
