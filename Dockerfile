# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables (fixing the legacy warning)
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app/

# Expose the port the app runs on
EXPOSE 5000

# Run the application (use JSON format for CMD to avoid signal issues)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "medirc_backend.wsgi:application"]
