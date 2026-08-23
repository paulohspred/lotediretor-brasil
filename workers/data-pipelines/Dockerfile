FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends gdal-bin unzip ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY workers/data-pipelines/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/data-pipelines/connectors.py .
COPY workers/data-pipelines/main.py .
CMD ["python","main.py"]
