# Use Python 3.11 slim base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir groq fastapi requests uvicorn python-multipart pocketbase python-dotenv

# Install necessary tools
RUN apt-get update && \
    apt-get install -y curl unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Download pre-built PocketBase (latest version)
RUN mkdir -p /pb && \
    curl -L https://github.com/pocketbase/pocketbase/releases/download/v0.25.8/pocketbase_0.25.8_linux_amd64.zip -o /tmp/pocketbase.zip && \
    unzip /tmp/pocketbase.zip -d /pb && \
    rm /tmp/pocketbase.zip && \
    chmod +x /pb/pocketbase

# Create directories for PocketBase
RUN mkdir -p /pb_data /pb_migrations

# Copy application code EXCEPT migrations
COPY *.py .
COPY *.html .
COPY requirements.txt* .

# Copy migrations to the correct location
COPY ./pb_migrations/* /pb_migrations/

# Create start script
RUN echo '#!/bin/bash' > /start.sh && \
    echo 'echo "Starting PocketBase..."' >> /start.sh && \
    echo '/pb/pocketbase serve --http="0.0.0.0:8090" --dir=/pb_data --migrationsDir=/pb_migrations --automigrate &' >> /start.sh && \
    echo 'POCKETBASE_PID=$!' >> /start.sh && \
    echo '' >> /start.sh && \
    echo 'echo "Waiting for PocketBase to start..."' >> /start.sh && \
    echo 'until $(curl --output /dev/null --silent --head --fail http://127.0.0.1:8090/api/health); do' >> /start.sh && \
    echo '  echo "Waiting for PocketBase to be ready..."' >> /start.sh && \
    echo '  sleep 2' >> /start.sh && \
    echo 'done' >> /start.sh && \
    echo '' >> /start.sh && \
    echo 'echo "Listing migration files to confirm:"' >> /start.sh && \
    echo 'ls -la /pb_migrations/' >> /start.sh && \
    echo '' >> /start.sh && \
    echo 'echo "Creating superuser account..."' >> /start.sh && \
    echo '/pb/pocketbase superuser upsert admin@example.com password123' >> /start.sh && \
    echo 'sleep 5' >> /start.sh && \
    echo '' >> /start.sh && \
    echo 'echo "Starting FastAPI application..."' >> /start.sh && \
    echo 'export POCKETBASE_URL="http://127.0.0.1:8090"' >> /start.sh && \
    echo 'uvicorn app:app --host 0.0.0.0 --port 8000' >> /start.sh && \
    chmod +x /start.sh

# Expose ports for FastAPI and PocketBase
EXPOSE 8000 8090

# Run both services
CMD ["/start.sh"]