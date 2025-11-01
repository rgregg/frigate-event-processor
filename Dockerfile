# Use a lightweight Python image
FROM python:3.12-slim

# Set a working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application into the container
COPY src ./src

WORKDIR /app/src

# Add health check instruction
ENV DOCKER_HEALTH_ENABLED=true
ENV DOCKER_HEALTH_HOST=127.0.0.1
ENV DOCKER_HEALTH_PORT=59123
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD ["python", "/app/src/health_checker.py"]

# Set the default command to run the app
CMD ["python", "-m", "frigate_event_processor.main"]

