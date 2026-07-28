FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    ffmpeg \
    curl \
    clinfo \
    intel-opencl-icd \
    intel-media-va-driver-non-free \
    libze1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    websockets \
    faster-whisper \
    openai \
    duckduckgo_search \
    openvino \
    optimum[intel]

COPY app/ /app/

RUN mkdir -p /app/custom

EXPOSE 8765

CMD ["python", "server.py"]
