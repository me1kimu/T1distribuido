FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY README.md ./README.md

ENV PYTHONPATH=/app

CMD ["uvicorn", "src.cache_service:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning", "--no-access-log"]
