# 📋 Cyber Girlfriend (賽博女友) 開發與任務紀錄

本文檔記錄 **Cyber Girlfriend** 專案 v1.5 / v2.0 的完成事項與目前 Debug 調優進度。

---

## 🎉 v1.5 完成與最新實裝功能 (Implemented Features)

- [x] **SQLite 本地持久化長期記憶 (Long-Term Memory)**
  - 於 `/app/custom/girlfriend_memory.db` 建立 SQLite 記憶庫，對話上下文自動持久化存儲於 N100 宿主機。
- [x] **Google `text-embedding-004` 語意向量意圖路由器 (Semantic Intent Router)**
  - 計算用戶話語與搜尋錨點的餘弦相似度 (Cosine Similarity)，當 Score > 0.45 時自動觸發 DuckDuckGo 網路搜尋。
  - 具備 Google API 網路波動時的雙重容錯降級機制 (Hybrid Fallback Matcher)。
- [x] **mac-voice-input 黃金 Prompt 移植 (Typeless Style STT Correction)**
  - 移植來自 `mac-voice-input` 的極速語音輸入法修正 Prompt。
  - 自動過濾口語贅字（「呃/然後/對」），自動完成繁體標點符號與語意修飾。
- [x] **純動態拼字說明與無硬編碼泛化架構 (Generic Dynamic Architecture)**
  - 徹底移除所有程式碼硬寫死的名詞（如「阿龐/阿胖山/山海燉」）。
  - 升級 Prompt 支持動態拆字/字形說明解讀（例如「胖是肥胖的胖，山是山脈的山」），自動拼寫正確正字。
  - 搜尋關鍵字提煉自動針對 YouTube / 網紅 / 影片補充 `YouTube` 搜尋詞與 `title` 資訊。

---

## 🛠️ 目前 Debug 調優進度紀錄 (Debug Progress - 2026/07/27)

### 📌 已完成排查與修復 (Resolved Issues):
1. **Google Embedding 404 URL 修復**：修復 `text-embedding-004` REST endpoint 格式。
2. **上下文關鍵字提煉代詞指代問題**：修復「他今天發表的影片是什麼」無法指代上文主體的問題，現在提取器會帶入對話 Context 提煉完整搜尋詞（例如 `阿胖山 YouTube 最新影片`）。
3. **LLM 憑空捏造 (Hallucination) 防護**：硬性規定當 DuckDuckGo 摘要無具體標題時，LLM 必須實話實說，嚴禁憑空猜測標題或菜名。
4. **SQLite 髒記憶擦除**：已於 N100 宿主機清除舊版測試殘留的胡編亂造記憶檔 (`girlfriend_memory.db`)。

### ⏳ 明天待繼續測試與驗證事項 (Next Actions for Tomorrow):
1. **實測真實 YouTube 影片搜尋**：連線 `https://gf.3pm.lol` 測試詢問熱門與長尾 YouTuber（如「阿胖山 山海燉」或最新影片），驗證 DuckDuckGo 摘要擷取與 LLM 回覆準確度。
2. **測試拼字口述修正**：測試對著麥克風講「A是XX的A，B是YY的B」時，Typeless 語義修正層是否能 100% 動態拼出正字。
3. **長時記憶連貫性調優**：觀察多輪對話後 SQLite 歷史記憶是否乾淨、無污染。

---

## 🔮 v2.0 待辦與升級規劃 (TODO for v2.0)

- [ ] **Wav2Lip / LivePortrait 3D 動態驅動**
  - 引入 `LivePortrait` 或 `Wav2Lip` 驅動器，實現講話時頭部自然傾斜、點頭與 3D 口型開合。
- [ ] **多硬體加速後端切換器 (Multi-Backend Hardware Selector)**
  - 提供設定選單：`CPU (Default)` / `NVIDIA CUDA` / `Intel OpenVINO` / `AMD ROCm` / `Apple Silicon MPS`。
- [ ] **多人設與自訂 LLM/TTS API 彈窗**
  - 前端 ⚙️ Settings 選單，支援切換 DeepSeek / Kimi / Ollama 或替換自訂語音 ID。
