FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY backend /app/backend

RUN pip install --no-cache-dir .

ENV SYNAPSE_DATA_DIR=/data
EXPOSE 8717

CMD ["uvicorn", "synapse.main:app", "--host", "0.0.0.0", "--port", "8717"]

