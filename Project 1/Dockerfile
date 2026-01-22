FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for torch and ML libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Create data and reports directories
RUN mkdir -p /app/data /app/reports

# Expose API port
EXPOSE 8000

# Default command (can be overridden)
CMD ["python", "main.py", "api"]
