FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY price_ids.yaml ./

RUN pip install --no-cache-dir -e .

EXPOSE 8090

CMD ["sh", "-c", "uvicorn src.app:app --host 0.0.0.0 --port ${PORT:-8090}"]
