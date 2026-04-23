FROM python:3.12-slim

WORKDIR /app

# Install system deps for Playwright (only if URL audits are used)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Make entrypoint executable
RUN chmod +x /app/github-action/entrypoint.sh

ENTRYPOINT ["/app/github-action/entrypoint.sh"]
