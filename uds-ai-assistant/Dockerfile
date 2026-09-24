# Multi-purpose image: API by default; override CMD to run the UI or the CLI.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY uds_assistant ./uds_assistant
COPY data ./data

RUN pip install --no-cache-dir -e .

ENV UDS_DATA_DIR=/app/data
EXPOSE 8000 8501

CMD ["uds-ai", "serve", "--host", "0.0.0.0", "--port", "8000"]
