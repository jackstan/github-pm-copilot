FROM python:3.9-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (usually optional; safe baseline)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# Install python deps first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Render provides PORT; Streamlit needs to bind to 0.0.0.0
EXPOSE 8080
ENV PORT=8080

CMD ["bash", "-lc", "streamlit run app.py --server.port=$PORT --server.address=0.0.0.0"]
