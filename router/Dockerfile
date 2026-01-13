FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY logging_utils.py .
COPY config ./config
COPY services ./services
COPY http_handlers ./http_handlers
COPY routes.yml .

ENV PYTHONPATH=/app

# Run as non-root user
RUN useradd -m -u 1000 webhook && chown -R webhook:webhook /app
USER webhook

EXPOSE 8091

CMD ["python", "app.py"]
