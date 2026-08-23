FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ocrmypdf tesseract-ocr tesseract-ocr-por && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY workers/documents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/documents/main.py .
CMD ["python","main.py"]
