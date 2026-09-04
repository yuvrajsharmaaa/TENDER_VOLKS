FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# Install OpenCV dependencies (libgl1, libglib2.0-0, libgomp1) and the Tesseract OCR
# engine binary as fallback (required by pytesseract in ocr/ocr_engine.py).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    && rm -rf /var/lib/apt/lists/*

# Optimize OpenMP and Paddle memory allocation to prevent CPU thread starvation and OOM
ENV OMP_NUM_THREADS=1
ENV FLAGS_allocator_strategy=naive_best_fit
ENV PADDLE_OCR_ENABLED=true

# Pre-download pre-trained PaddleOCR detection, recognition, and angle classifier models
# directly into the image so runtime requests never face network downloads or timeouts
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='en')"


# Copy application source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start application using Uvicorn with auto-reload for development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
