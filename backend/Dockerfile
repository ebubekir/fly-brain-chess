FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && useradd --uid 10001 --create-home app
COPY --chown=app:app app ./app
COPY --chown=app:app data ./data
USER app
EXPOSE 8001
HEALTHCHECK --interval=20s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1", "--ws-max-size", "2048", "--ws-max-queue", "8", "--limit-concurrency", "160", "--timeout-graceful-shutdown", "10", "--no-access-log"]
