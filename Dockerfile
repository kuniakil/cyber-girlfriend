FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    ffmpeg \
    curl \
    intel-opencl-icd \
    intel-igc-core \
    intel-igc-opencl \
    ocl-icd-libopencl1 \
    && groupadd -g 990 render || true \
    && usermod -aG video root || true \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m pip install --no-cache-dir --break-system-packages \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN python3 -m pip install --no-cache-dir --break-system-packages \
    fastapi \
    uvicorn \
    websockets \
    faster-whisper \
    openai \
    duckduckgo_search \
    optimum[onnxruntime] \
    && python3 -m pip uninstall -y onnxruntime \
    && python3 -m pip install --no-cache-dir --break-system-packages onnxruntime-openvino

COPY app/ /app/

RUN mkdir -p /app/custom

EXPOSE 8765

CMD ["python3", "server.py"]
