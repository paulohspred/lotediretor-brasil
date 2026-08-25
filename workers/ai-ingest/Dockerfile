FROM python:3.13-slim
WORKDIR /app
COPY workers/ai-ingest/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/ai-ingest/main.py workers/ai-ingest/index_schema.py ./
CMD ["python","main.py"]
