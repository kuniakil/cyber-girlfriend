FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    clinfo \
    intel-opencl-icd \
    intel-igc-core \
    intel-igc-opencl \
    && groupadd -g 990 render || true \
    && usermod -aG video root || true \
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
    optimum[onnxruntime] \
    && pip uninstall -y onnxruntime \
    && pip install --no-cache-dir onnxruntime-openvino==1.24.1

COPY app/ /app/

RUN mkdir -p /app/custom

EXPOSE 8765

CMD ["python", "server.py"]
