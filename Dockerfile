# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy session file
COPY session.session .

# Create non-root user for security first
RUN adduser --disabled-password --gecos '' --uid 1000 botuser

# Create directories for persistent storage and set proper ownership
RUN mkdir -p /app/data /app/logs && \
    chown -R botuser:botuser /app && \
    chmod -R 755 /app/data /app/logs

# Switch to non-root user
USER botuser

# Expose port (not necessary for Telegram bot but good practice)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('https://api.telegram.org/bot${BOT_TOKEN}/getMe')" || exit 1

# Run the bot
CMD ["python", "main.py"] 