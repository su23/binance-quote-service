FROM python:3.13-slim AS base

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 8000

ENTRYPOINT ["quote-service"]
