# 💕 Cyber Girlfriend (賽博女友 v1.0 MVP)

An interactive, hands-free Real-Avatar AI Cyber Girlfriend powered by **faster-whisper (STT)**, **MiniMax LLM**, and **MiniMax T2A Voice Clone**.

![Cyber Girlfriend Demo](https://img.shields.io/badge/License-MIT-blue.svg) ![Docker Build](https://img.shields.io/badge/Docker-GHCR-blue?logo=docker)

---

## 🌟 Key Features

- **🎙️ Hands-Free Gemini-Style Voice Mode**: Automatic VAD (Voice Activity Detection) with silence-based auto-sending (1.2s pause) and 10s auto-guard limit.
- **🗣️ Voice Cloning (MiniMax T2A)**: Zero-shot voice cloning with natural emotion and breathing tone.
- **📸 Photorealistic Visual Avatar**: Fullscreen video-call UI with dynamic subtle pulse effects.
- **🛑 Smart Microphone Controls**: Instant hardware microphone release on stop.
- **⚡ Lightweight CPU & GPU Accelerated**: Optimized with `faster-whisper` (int8) and Intel OpenVINO / QSV (`/dev/dri`) support for N100 or mini PCs.

---

## 🚀 Quick Start with Docker Compose

### 1. Clone the repository
```bash
git clone https://github.com/kuniakil/cyber-girlfriend.git
cd cyber-girlfriend
```

### 2. Prepare your Assets (Optional)
Create a `custom_assets` directory and place your favorite female avatar photo:
```bash
mkdir -p custom_assets
cp /path/to/your_face.png custom_assets/face.png
```

### 3. Run with Docker Compose
Edit `docker-compose.yml` to set your `MINIMAX_API_KEY`, then run:
```bash
docker compose up -d
```

Open your browser at **`http://localhost:8765`** and click **Connect**!

---

## 🎙️ How to Clone Your Own Cyber Girlfriend Voice

1. Prepare a 15-30s clean, noise-free, BGM-free MP3/WAV audio clip of your target voice.
2. Upload and register the voice using MiniMax Voice Clone API:
```bash
# 1. Upload audio file
curl -X POST "https://api.minimaxi.chat/v1/files/upload" \
  -H "Authorization: Bearer YOUR_MINIMAX_API_KEY" \
  -F "purpose=voice_clone" \
  -F "file=@your_voice.mp3"

# 2. Register Voice Clone
curl -X POST "https://api.minimaxi.chat/v1/voice_clone" \
  -H "Authorization: Bearer YOUR_MINIMAX_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "voice_id": "cyber_girlfriend_custom_v1",
    "file_id": 123456789
  }'
```
3. Set `MINIMAX_VOICE_ID=cyber_girlfriend_custom_v1` in your environment variables.

---

## 🗺️ Roadmap & Future Upgrades (v2.0)

- [ ] **v2.0**: Integration of **Wav2Lip / LivePortrait** for real-time 3D head motion and lip-syncing.
- [ ] **v2.1**: Multi-Backend Hardware Selector (NVIDIA CUDA / Intel OpenVINO / AMD ROCm / Apple MPS).

---

## 📄 License
MIT License
