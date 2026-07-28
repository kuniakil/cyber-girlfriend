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

# Install Intel GPU drivers from GitHub releases.
#
# IMPORTANT: `intel-opencl-icd` MUST be extracted manually (dpkg-deb -x) rather than
# installed via dpkg, because Debian trixie's apt repo also has a (much older) version
# of `intel-opencl-icd`, and `apt-get install -f -y` would silently remove our newer
# GitHub-release version, leaving no `libigdrcl.so` on the system and breaking OpenVINO
# GPU initialization ("[OpenVINO] Device GPU is not available").
#
# IGC and libigdgmm12 don't conflict with apt repo packages, so we install them via dpkg.
RUN set -eux \
    && mkdir -p /tmp/intel-gpu && cd /tmp/intel-gpu \
    && wget -q https://github.com/intel/intel-graphics-compiler/releases/download/igc-1.0.17537.24/intel-igc-core_1.0.17537.24_amd64.deb \
    && wget -q https://github.com/intel/intel-graphics-compiler/releases/download/igc-1.0.17537.24/intel-igc-opencl_1.0.17537.24_amd64.deb \
    && wget -q https://github.com/intel/compute-runtime/releases/download/26.22.38646.4/libigdgmm12_22.10.0_amd64.deb \
    && dpkg -i ./intel-igc-core_*.deb ./intel-igc-opencl_*.deb ./libigdgmm12_*.deb || apt-get install -f -y \
    && rm -f ./intel-igc-core_*.deb ./intel-igc-opencl_*.deb ./libigdgmm12_*.deb \
    \
    && echo "=== Phase B: manual extraction of intel-opencl-icd (bypasses apt conflict) ===" \
    && wget -q https://github.com/intel/compute-runtime/releases/download/26.22.38646.4/intel-opencl-icd_26.22.38646.4-0_amd64.deb \
    && dpkg-deb -x intel-opencl-icd_26.22.38646.4-0_amd64.deb /tmp/intel-opencl-extract \
    && mkdir -p /usr/lib/x86_64-linux-gnu/intel-opencl /etc/OpenCL/vendors \
    && cp /tmp/intel-opencl-extract/usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so /usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so \
    && echo "/usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so" > /etc/OpenCL/vendors/intel.icd \
    && ldconfig \
    && test -f /usr/lib/x86_64-linux-gnu/intel-opencl/libigdrcl.so || (echo "FATAL: libigdrcl.so not extracted correctly" && exit 1) \
    && rm -f intel-opencl-icd_*.deb && rm -rf /tmp/intel-opencl-extract \
    \
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
