FROM python:3.11-slim
WORKDIR /app
RUN apt-get update -qq && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY exporter.py .
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:9420/health || exit 1
EXPOSE 9420
CMD ["python", "exporter.py"]
