FROM python:3.12-slim

WORKDIR /app

# System deps for reportlab/PyMuPDF are pure-python; keep image lean.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV UPLOAD_DIR=/app/uploads
RUN mkdir -p /app/uploads

EXPOSE 8000
# Render (and similar hosts) inject $PORT — default to 8000 for docker compose.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
