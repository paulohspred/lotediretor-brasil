FROM python:3.13-slim
WORKDIR /app
COPY workers/rural-monitor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && groupadd --system lotediretor \
 && useradd --system --gid lotediretor --home-dir /app --shell /usr/sbin/nologin lotediretor
COPY --chown=lotediretor:lotediretor workers/rural-monitor/main.py .
USER lotediretor
CMD ["python","main.py"]
