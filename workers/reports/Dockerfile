FROM python:3.13-slim
WORKDIR /app
COPY workers/reports/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/reports/main.py workers/reports/builder.py workers/reports/renderer.py ./
CMD ["python","main.py"]
