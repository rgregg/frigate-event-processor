# Use a lightweight Python image
FROM python:3.12-slim

# Set a working directory inside the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Python application into the container
COPY *.py .

# Set the default command to run the app
CMD ["python", "mqtt_processor.py"]

