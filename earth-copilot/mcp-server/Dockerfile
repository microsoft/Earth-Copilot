# Earth-Copilot MCP Server
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY mcp_bridge.py .
COPY __init__.py .

# Create directory for logs
RUN mkdir -p /app/logs

# Expose port for HTTP bridge
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Run the HTTP bridge
CMD ["python", "-m", "uvicorn", "mcp_bridge:app", "--host", "0.0.0.0", "--port", "8080"]
