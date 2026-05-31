# Use Python 3.11 base image (required for semantic-kernel>=1.0.0)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for geospatial processing
# GDAL is required for rasterio to read COG files (terrain analysis)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libexpat1 \
    libexpat1-dev \
    libgeos-dev \
    libxml2 \
    libxml2-dev \
    gdal-bin \
    libgdal-dev \
    libproj-dev \
    proj-bin \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables for rasterio
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
# Skip netCDF driver — it requires userfaultfd (blocked by Docker seccomp).
# HDF5 driver reads the same NetCDF4 files without this restriction.
ENV GDAL_SKIP=netCDF

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port 8080 (must match Azure Container App targetPort configuration)
EXPOSE 8080

# Run the FastAPI application with uvicorn on port 8080
# Using 4 workers to handle concurrent requests (especially important for AI/LLM calls)
CMD ["uvicorn", "fastapi_app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "4"]
