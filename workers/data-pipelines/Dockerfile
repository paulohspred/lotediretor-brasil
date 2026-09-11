FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends gdal-bin unzip ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY workers/data-pipelines/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && groupadd --system lotediretor \
 && useradd --system --gid lotediretor --home-dir /app --shell /usr/sbin/nologin lotediretor
COPY --chown=lotediretor:lotediretor workers/data-pipelines/connectors.py .
COPY --chown=lotediretor:lotediretor workers/data-pipelines/main.py .
USER lotediretor
CMD ["python","main.py"]
