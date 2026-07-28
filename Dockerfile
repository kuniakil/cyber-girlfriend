FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV LIBVA_DRIVER_NAME=iHD
ENV OPENVINO_LOG_LEVEL=1

# Install base system packages (python3, ffmpeg, OpenCL loader)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    ffmpeg \
    curl \
    wget \
    ocl-icd-libopencl1 \
    && rm -rf /var/lib/apt/lists/*

# Install Intel GPU drivers from GitHub releases (same approach as Immich ML)
RUN mkdir -p /tmp/intel-gpu && cd /tmp/intel-gpu \
    && wget -q https://github.com/intel/intel-graphics-compiler/releases/download/igc-1.0.17537.24/intel-igc-core_1.0.17537.24_amd64.deb \
    && wget -q https://github.com/intel/intel-graphics-compiler/releases/download/igc-1.0.17537.24/intel-igc-opencl_1.0.17537.24_amd64.deb \
    && wget -q https://github.com/intel/compute-runtime/releases/download/26.22.38646.4/intel-opencl-icd_26.22.38646.4-0_amd64.deb \
    && wget -q https://github.com/intel/compute-runtime/releases/download/26.22.38646.4/libigdgmm12_22.10.0_amd64.deb \
    && dpkg -i ./*.deb || apt-get install -f -y \
    && rm -rf /tmp/intel-gpu \
    && groupadd -g 990 render || true \
    && usermod -aG video root || true

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    websockets \
    faster-whisper \
    openai \
    duckduckgo_search \
    optimum[onnxruntime] \
    transformers \
    && pip uninstall -y onnxruntime \
    && pip install --no-cache-dir onnxruntime-openvino

COPY app/ /app/

RUN mkdir -p /app/custom

EXPOSE 8765

CMD ["python3", "server.py"]
