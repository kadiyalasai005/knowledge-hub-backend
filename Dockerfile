# Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# ---> ADD THESE LINES to install build tools <---
# build-essential & gcc provide compilers needed for C extensions
# Add libpq-dev if you suspect psycopg2 compilation issues:
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc libpq-dev && rm -rf /var/lib/apt/lists/*
# ---> END ADD <---

# Install system dependencies (if any are needed - e.g., for psycopg2 build sometimes)

# Install Python dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code into the container
COPY . .

# Expose port FastAPI will run on (doesn't actually publish it, docker-compose does that)
EXPOSE 8000

# Default command to run FastAPI (can be overridden in docker-compose)
# Use 0.0.0.0 to listen on all interfaces within the container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]