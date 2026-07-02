FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including those required for cryptography and post-quantum crypto
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    ninja-build \
    libssl-dev \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Note: In a true production environment, liboqs should be compiled from source here.
# For demonstration, we assume python packages cover our needs or we fallback to AES if liboqs fails.
# RUN git clone -b main https://github.com/open-quantum-safe/liboqs.git && \
#     cd liboqs && mkdir build && cd build && cmake -GNinja .. && ninja && ninja install

COPY requirements.txt .
# Disable caching for smaller images
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src /app/src

# Setup non-root user for security
RUN useradd -m jarvisuser
USER jarvisuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
