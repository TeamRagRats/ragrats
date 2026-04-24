FROM nvidia/cuda:13.0.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    libreoffice \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --pre \
    torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu130

RUN pip3 install --no-cache-dir \
    docling \
    psycopg[binary] \
    psutil \
    pynvml \
    python-dotenv

WORKDIR /app
