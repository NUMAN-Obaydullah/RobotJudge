FROM python:3.12-slim

# System deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Install the robotjudge package in editable mode
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "web/server.py"]
