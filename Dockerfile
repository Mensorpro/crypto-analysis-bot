FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Render sets PORT dynamically — EXPOSE is informational only
EXPOSE 10000

# Run bot + dashboard (Flask serves on $PORT)
CMD ["python", "run.py"]
