FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install curl for container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create persistence data directory
RUN mkdir -p /app/data

# Default configuration
ENV PORT=8000
ENV COMMAND_LOG_PATH=/app/data/command_log.jsonl

EXPOSE 8000

CMD ["python", "main.py"]

