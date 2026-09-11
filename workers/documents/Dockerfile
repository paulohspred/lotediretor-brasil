FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends ocrmypdf tesseract-ocr tesseract-ocr-por && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY workers/documents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && groupadd --system lotediretor \
 && useradd --system --gid lotediretor --home-dir /app --shell /usr/sbin/nologin lotediretor
COPY --chown=lotediretor:lotediretor workers/documents/main.py workers/documents/rules.py workers/documents/chunking.py ./
USER lotediretor
CMD ["python","main.py"]
