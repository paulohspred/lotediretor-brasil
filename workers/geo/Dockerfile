FROM python:3.13-slim
WORKDIR /app
COPY workers/geo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/geo/main.py .
CMD ["python","main.py"]
