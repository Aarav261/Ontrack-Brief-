FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# ONE worker (APScheduler must run in exactly one process), but threaded so the
# single process serves many requests concurrently — without it the sync worker
# handles one request at a time and a slow OnTrack call blocks everyone.
# Shell form so ${PORT} (injected by Railway) expands; falls back to 8000 locally.
CMD gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --worker-class gthread --threads 8 --timeout 120 app:app
