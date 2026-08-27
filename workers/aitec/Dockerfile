FROM python:3.12-slim
WORKDIR /app
COPY workers/aitec/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY workers/aitec/main.py /app/main.py
CMD ["python","/app/main.py"]
