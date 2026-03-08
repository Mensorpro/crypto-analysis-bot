FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Render injects PORT env var (default 10000)
EXPOSE ${PORT:-10000}

# Run bot + dashboard
CMD ["python", "run.py"]

