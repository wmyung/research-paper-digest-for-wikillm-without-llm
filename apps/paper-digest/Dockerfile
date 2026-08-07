FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.lock \
    && python -m pip install --no-deps .

RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8088
CMD ["sh", "-c", "uvicorn paper_digest.api:app --host 0.0.0.0 --port ${PORT:-8088} --workers 1"]
