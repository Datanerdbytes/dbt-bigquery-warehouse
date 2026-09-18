# 1. Base image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# 2. Install uv and gunicorn
RUN pip install --no-cache-dir uv gunicorn

# 3. Copy dependency configs from project root
COPY pyproject.toml uv.lock ./

# 4. Install dependencies
RUN uv pip install --system --no-cache -r pyproject.toml

# 5. Copy the entire repository into /app
COPY . .

# 6. Set working directory to my-dash-app where app.py lives
WORKDIR /app/my-dash-app

# 7. Run via Gunicorn production WSGI server (JSON Array format)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "app:server"]
