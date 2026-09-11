FROM python:3.12-slim
WORKDIR /app
COPY workers/aitec/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
 && groupadd --system lotediretor \
 && useradd --system --gid lotediretor --home-dir /app --shell /usr/sbin/nologin lotediretor
COPY --chown=lotediretor:lotediretor workers/aitec/main.py /app/main.py
USER lotediretor
CMD ["python","/app/main.py"]
