FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create a non-root user (Hugging Face Spaces requires this for security)
RUN useradd -m -u 1000 user

# Install system dependencies required for ChromaDB and building python packages
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libffi-dev \
    libssl-dev \
    libgomp1 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip

# Copy requirements and install them
COPY --chown=user:user requirements.txt .

# Install packages in stages to isolate errors
RUN pip install --no-cache-dir cloudinary
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY --chown=user:user . .

# Switch to the non-root user
USER user

# Hugging Face Spaces run on port 7860 by default
EXPOSE 7860

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
