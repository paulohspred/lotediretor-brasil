FROM python:3.13-slim
WORKDIR /app
COPY workers/geo/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && groupadd --system lotediretor \
 && useradd --system --gid lotediretor --home-dir /app --shell /usr/sbin/nologin lotediretor
COPY --chown=lotediretor:lotediretor workers/geo/main.py .
USER lotediretor
CMD ["python","main.py"]
