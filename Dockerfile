FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y libvips libvips-tools && \
    rm -rf /var/lib/apt/lists/*

COPY panoconfig360_backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV VIPS_CONCURRENCY=0

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "panoconfig360_backend.api.server:app", "--bind", "0.0.0.0:10000", "--workers", "1", "--threads", "1", "--timeout", "120", "--graceful-timeout", "120"]