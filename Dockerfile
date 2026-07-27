FROM python:3.11-slim

# 安裝系統層級必要依賴 (ffmpeg, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先安裝 PyTorch CPU 版本，避免下載多餘的 CUDA 套件
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 安裝 FastAPI, Whisper, OpenAI client
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    websockets \
    faster-whisper \
    openai

# 複製應用程式碼
COPY app/ /app/

# 建立放自訂素材的資料夾
RUN mkdir -p /app/custom

EXPOSE 8765

CMD ["python", "server.py"]
