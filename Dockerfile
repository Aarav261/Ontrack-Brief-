FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Single worker required — APScheduler must run in exactly one process.
# Shell form so ${PORT} (injected by Railway) expands; falls back to 8000 locally.
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 app:app
