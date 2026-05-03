FROM python:3.11-slim

WORKDIR /app

# ✅ Copy requirements first
COPY requirements.txt .

# ✅ Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy frontend code
COPY . .

ENV PYTHONUNBUFFERED=1


CMD streamlit run app.py --server.port=$PORT --server.address=0.0.0.0