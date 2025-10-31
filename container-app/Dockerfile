# Use Python 3.11 base image (required for semantic-kernel>=1.0.0)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal set for geospatial libraries)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgeos-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port 8080 (must match Azure Container App targetPort configuration)
EXPOSE 8080

# Run the FastAPI application with uvicorn on port 8080
# Increased timeouts for long-running GPT-5 Vision API calls
CMD ["uvicorn", "fastapi_app:app", "--host", "0.0.0.0", "--port", "8080", "--timeout-keep-alive", "300", "--timeout-graceful-shutdown", "30"]
