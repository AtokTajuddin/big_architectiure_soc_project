FROM python:3.11-slim
WORKDIR /app
COPY monitor.py /app/monitor.py
# monitor.py stdlib-only (urllib) — tanpa dependency tambahan
EXPOSE 8899
CMD ["python3", "/app/monitor.py"]
