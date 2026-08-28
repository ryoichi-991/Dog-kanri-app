FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-jpn \
    tesseract-ocr-deu \
    tesseract-ocr-fra \
    tesseract-ocr-ita \
    tesseract-ocr-spa \
    tesseract-ocr-por \
    tesseract-ocr-nld \
    tesseract-ocr-pol \
    tesseract-ocr-ces \
    tesseract-ocr-hun \
    tesseract-ocr-rus \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
