FROM python:3.11-slim

WORKDIR /app

# System dependencies for OpenCV, PyMuPDF, and Tesseract OCR
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

RUN mkdir -p uploads exports instance

EXPOSE 5000

CMD ["python", "app.py"]
