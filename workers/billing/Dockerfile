FROM python:3.13-slim
WORKDIR /app
COPY workers/billing/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/billing/main.py .
CMD ["python","main.py"]
