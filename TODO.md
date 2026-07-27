# 📋 Cyber Girlfriend (賽博女友) 開發與任務紀錄

本文檔記錄 **Cyber Girlfriend** 專案 v1.0 MVP 的完成事項與 v2.0 的後續升級規劃。

---

## 🎉 v1.0 MVP 完成事項 (Completed Features)

- [x] **語音與對話管線 (Voice & Dialogue Pipeline)**
  - 整合 `faster-whisper` (base, int8) 本地 CPU/GPU 語音轉文字 (STT)。
  - 整合 `MiniMax-Text-01` 大語言模型 API。
  - 整合 `MiniMax T2A Voice Clone` 零樣本聲音克隆 (`cyber_girlfriend_custom_v1`)。
- [x] **Gemini 免手動語音模式 (Hands-Free Voice Mode)**
  - 實作前端 Web Audio VAD 靜音自動斷句 (1.2 秒靜音自動發送)。
  - 實作 10 秒安全超時與對話結束後自動續播/自動開啟下一輪聆聽機制。
  - 新增 `🛑 Stop / Release Mic` 按鈕，徹底釋放 Mac/瀏覽器硬體麥克風音訊軌 (`track.stop()`)。
- [x] **全螢幕擬真視訊 UI (Immersive Video UI)**
  - 巨幅全螢幕視訊介面，極簡半透明底部字幕。
  - 靜止高清真人頭像，並使用 Web Audio API `GainNode` 強效放大音量至 3.5 倍。
- [x] **N100 硬體加速 (Hardware Acceleration)**
  - 部署檔掛載 N100 宿主機 `/dev/dri` (Intel UHD Graphics QSV/OpenVINO)。
  - 設定 `supplementalGroups: [44, 990]` 與特權模式取得顯卡讀寫權限 (`Writable GPU!`)。
- [x] **開源分離與 DevOps CI/CD**
  - 開發檔與 K8s 部署檔解耦（獨立倉庫 `cyber-girlfriend` 與 `my-k8s`）。
  - `.gitignore` 與 `.dockerignore` 雙重隔離金鑰與個人素材。
  - 設定 GitHub Actions 自動編譯 Docker Image 並推送到 `ghcr.io/kuniakil/cyber-girlfriend:main`。
- [x] **K3s 生產環境部署**
  - 配置 `gf.3pm.lol` 獨立 Ingress 並套用現有 `wildcard-3pm-lol-tls` 憑證 (HTTPS)。

---

## 🔮 v2.0 待辦與升級規劃 (TODO for v2.0)

- [ ] **Wav2Lip / LivePortrait 3D 動態驅動**
  - 引入 `LivePortrait` 或 `Wav2Lip` 驅動器，實現講話時頭部自然傾斜、點頭與 3D 口型開合。
- [ ] **多硬體加速後端切換器 (Multi-Backend Hardware Selector)**
  - 提供設定選單：`CPU (Default)` / `NVIDIA CUDA` / `Intel OpenVINO` / `AMD ROCm` / `Apple Silicon MPS`。
  - 實作自動降級 (Auto-Fallback) 防護機制。
- [ ] **多人設與自訂 LLM/TTS API 彈窗**
  - 前端 ⚙️ Settings 選單，支援切換 DeepSeek / Kimi / Ollama 或替換自訂語音 ID。
