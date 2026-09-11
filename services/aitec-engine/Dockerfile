FROM python:3.13-slim
WORKDIR /app
COPY services/aitec-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && groupadd --system lotediretor \
 && useradd --system --gid lotediretor --home-dir /app --shell /usr/sbin/nologin lotediretor
COPY --chown=lotediretor:lotediretor services/aitec-engine/app ./app
USER lotediretor
EXPOSE 8002
CMD ["uvicorn","app.entrypoint:app","--host","0.0.0.0","--port","8002"]
