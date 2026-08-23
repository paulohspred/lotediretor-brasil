FROM python:3.13-slim
WORKDIR /app
COPY workers/rural-monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/rural-monitor/main.py .
CMD ["python","main.py"]
