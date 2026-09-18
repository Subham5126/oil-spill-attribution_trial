FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including geospatial libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgdal-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir fastapi uvicorn pydantic python-dotenv sqlalchemy alembic geoalchemy2 celery redis "psycopg[binary]"

# Copy application source
COPY . .

EXPOSE 8000

CMD ["/bin/sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]


