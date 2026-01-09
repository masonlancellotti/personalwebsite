FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Uses ECS PORT if set, else 5000
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-5000} app:app"]