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
    && groupadd -g 990 render || true \
    && usermod -aG video root || true \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m pip install --no-cache-dir --upgrade pip

RUN python3 -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

RUN python3 -m pip install --no-cache-dir \
    fastapi \
    uvicorn \
    websockets \
    faster-whisper \
    openai \
    duckduckgo_search \
    optimum[onnxruntime] \
    && python3 -m pip uninstall -y onnxruntime \
    && python3 -m pip install --no-cache-dir onnxruntime-openvino==1.23.0

COPY app/ /app/

RUN mkdir -p /app/custom

EXPOSE 8765

CMD ["python3", "server.py"]
