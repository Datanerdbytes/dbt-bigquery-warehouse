# 1. Lightweight Python base image
FROM python:3.12-slim

# Prevent Python from writing .pyc files & enable unbuffered logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# 2. Install uv for fast dependency installation
RUN pip install --no-cache-dir uv gunicorn

# 3. Copy dependency definitions first (caching layer)
COPY pyproject.toml uv.lock ./

# 4. Install dependencies into system Python
RUN uv pip install --system --no-cache -r pyproject.toml

# 5. Copy application source code
COPY . .

# 6. Run via Gunicorn production WSGI server (JSON Array format)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "app:server"]
