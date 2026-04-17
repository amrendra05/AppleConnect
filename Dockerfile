# Use a lightweight Python image
FROM python:3.11-slim

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system deps (optional but often needed)
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your app code
COPY . .

# Expose port (Cloud Run uses 8080 by default)
EXPOSE 8080

# Run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]