# -----------------------------
# Base image
# -----------------------------
FROM python:3.12-slim

# Set workdir
WORKDIR /app

# Prevents Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Ensures stdout/stderr are flushed immediately
ENV PYTHONUNBUFFERED=1

# -----------------------------
# Install system dependencies
# -----------------------------
RUN apt-get update && \
    apt-get install -y gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

# -----------------------------
# Install python-getenv
# -----------------------------
RUN pip install --upgrade pip
RUN pip install python-dotenv

# -----------------------------
# Copy project files
# -----------------------------
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# -----------------------------
# Expose ports
# -----------------------------
EXPOSE 8000 5555 6379

# -----------------------------
# Entrypoint
# -----------------------------
# Default command is FastAPI uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
