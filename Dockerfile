FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./
COPY config.example.json ./config.json

# Create directory for database and logs
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
# Telegram credentials — set these at runtime, not build time:
# ENV TELEGRAM_BOT_TOKEN=your_token_here
# ENV TELEGRAM_CHAT_ID=your_chat_id_here

# Create non-root user
RUN useradd -m -u 1000 monitor && chown -R monitor:monitor /app
USER monitor

# Run the monitor
CMD ["python3", "main_monitor.py", "--service"]
