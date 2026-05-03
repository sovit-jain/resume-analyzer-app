FROM python:3.11-slim

WORKDIR /app

# Copy backend requirements only
COPY backend/requirements.txt .

# ✅ Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

ENV PYTHONUNBUFFERED=1

# Cloud Run compatible
CMD uvicorn main:app --host 0.0.0.0 --port $PORT