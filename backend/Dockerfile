# Web Observer backend: API, Dramatiq workers, and scheduler share this image.
# Playwright + Chromium are pre-installed so the browser_checks queue works
# out of the box inside the container.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=10

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Headless Chromium + required system libraries for the browser worker.
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8002

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
