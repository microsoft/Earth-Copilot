FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml server.py ./
RUN pip install --no-cache-dir -e .
ENV MCP_HOST=0.0.0.0 MCP_PORT=8765
EXPOSE 8765
CMD ["python", "server.py"]
