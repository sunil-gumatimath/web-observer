# Web Observer backend: API, Dramatiq workers, and scheduler share this image.
# Playwright + Chromium are pre-installed so the browser_checks queue works
# out of the box inside the container.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=30 \
    PIP_RETRIES=10 \
    PIP_ROOT_USER_ACTION=ignore \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# pip >= 26 resumes interrupted downloads; the pip bundled in the base image
# (25.0.1) crashes on a single read timeout, which is fatal on flaky
# Docker Desktop/WSL2 networks. The cache mount keeps already-downloaded
# wheels across retries without bloating the image.
RUN --mount=type=cache,target=/root/.cache/pip pip install --upgrade pip

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

# Headless Chromium + required system libraries for the browser worker.
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8002

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
