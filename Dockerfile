# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    ffmpeg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (required for YouTube JS challenges since yt-dlp 2025.11.12)
# Install to /usr/local so it's accessible to all users
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh

# Verify Deno is installed and accessible
RUN deno --version

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install yt-dlp nightly (--pre) for latest YouTube fixes
RUN pip install --no-cache-dir -U --pre "yt-dlp[default]"

# Copy the entire src directory and its structure
COPY src/ ./src/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port for HTTP mode
EXPOSE 3090

# Run the server using the new module structure
CMD ["python", "-m", "src.server.mcp_server", "--http"]
