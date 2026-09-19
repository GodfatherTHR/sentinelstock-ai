FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
ENV PYTHONUNBUFFERED=1
ENV CONNECTOR_SOURCES=maritime
CMD ["sh", "-c", "python -m app.worker ${CONNECTOR_SOURCES} --loop"]
