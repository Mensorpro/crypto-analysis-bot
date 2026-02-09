FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose dashboard port
EXPOSE 5000

# Run bot + dashboard
CMD ["python", "run.py"]
