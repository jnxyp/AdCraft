FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ /app/backend/

RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    aiosqlite \
    chromadb==1.5.8 \
    openai \
    pillow \
    python-dotenv \
    httpx \
    numpy

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
