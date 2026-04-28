FROM python:3.11-slim
WORKDIR /app
RUN apt-get update -qq && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -q pymysql
COPY exporter.py .
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:9419/health || exit 1
EXPOSE 9419
CMD ["python", "exporter.py"]
