FROM python:3.11-slim

WORKDIR /app

# ── System packages (tesseract already included, no paddle) ───
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1-mesa-glx \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        tesseract-ocr \
        tesseract-ocr-eng \
        curl \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ── App source ─────────────────────────────────────────────────
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
