#!/bin/bash
# Health check script for Planetary Explorer services

SERVICE_PORT=${PORT:-8080}
HEALTH_ENDPOINT=${HEALTH_ENDPOINT:-/health}

curl -f "http://localhost:${SERVICE_PORT}${HEALTH_ENDPOINT}" || exit 1
