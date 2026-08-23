FROM python:3.13-slim
WORKDIR /app
COPY workers/rural-export/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/rural-export/main.py workers/rural-export/exporter.py ./
CMD ["python","main.py"]
