# 📋 Cyber Girlfriend (賽博女友) 開發與任務紀錄

本文檔記錄 **Cyber Girlfriend** 專案 v1.5 / v1.7 / v2.0 的完成事項與持續 Debug 調優歷程。

---

## 🎉 v1.7 最新完成與調優事項 (Implemented & Debugged Features)

- [x] **SQLite 本地持久化長期記憶 (Long-Term Memory)**
  - 於 `/app/custom/girlfriend_memory.db` 建立 SQLite 記憶庫，對話上下文自動持久化存儲於 N100 宿主機。
- [x] **Google `text-embedding-004` 語意向量意圖路由器 (Semantic Intent Router)**
  - 計算用戶話語與搜尋錨點的餘弦相似度 (Cosine Similarity)，門檻值調優至 0.65，避免一般對話誤觸發外部搜尋。
- [x] **Typeless Style STT 語意與個人化字典修正**
  - 移植來自 `mac-voice-input` 的極速語音輸入法修正 Prompt。
  - 自動過濾口語贅字（「呃/然後/對」），自動完成繁體標點符號與語意修飾。
- [x] **個人化動態詞彙適應與自動學習機制 (User Glossary DB Learning)**
  - 於 SQLite 建立 `user_glossary` 資料表。
  - 自動捕捉並儲存使用者發送與修正的名詞（如：`阿胖山`、`福建莆田`、`劉偉元`）。
  - 將專屬熱詞動態注入 STT 糾錯 Prompts 中，實現「越用越懂你、錯誤率越來越低」的增量學習。
- [x] **Whisper `small` 模型升級與 CPU 多執行緒加速**
  - 將 `base` 模型升級為 `small` (int8 量化)，並配置 `cpu_threads=4` 平行運算，大幅提升地方地名與罕見俚語的原始辨識率。
- [x] **UI 雙模輸入與語音預覽機制 (Single Session Fix)**
  - 語音辨識出文字後僅在底部輸入框填入預覽，不自動送給 LLM。
  - 使用者可使用 `Typeless` 或鍵盤修正字詞後發送，確保每輪發言為唯一 Session，解決雙發送與雞同鴨講問題。
- [x] **音訊播放互斥鎖與單一 Session 播放保護 (Audio Mutual Exclusion Lock)**
  - AI 播放 TTS 時自動切斷麥克風並暫停 VAD 靜音檢測，播放完畢延遲 600ms 恢復，徹底杜絕喇叭殘音被錄入導致自言自語的迴圈。
  - 前端播放新音訊前自動切斷舊 Audio 物件，確保同時間僅有單一聲音播放。
- [x] **實時 CPU / GPU 溫度與硬體負載儀表板 (Hardware Metrics Dashboard)**
  - 後端新增 `/api/system_status` API，讀取 Linux sysfs (`/sys/class/thermal` 及 `/proc/stat`、`gt_act_freq_mhz`) 獲取 CPU 溫度、CPU 負載率與 iGPU 頻率/渲染使用率。
  - 前端頂部狀態列整合膠囊風指標 Badge (`🌡️ CPU: 53°C`, `💻 Load: 12%`, `🎮 GPU: 450 MHz`)，每 2 秒自動刷新。

---

## 🛠️ Debug 與問題排查歷程紀錄 (Continuous Debugging Log)

### 📌 已完成排查與修復 (Resolved Issues):
1. **[2026/07/27] 搜尋與對話記憶混淆/記憶斷層**：
   - **現象**：問「談過什麼」，AI 回覆無法記錄對話；搜尋外部資料（如小高姐）後，誤說成「我們剛才談過小高姐」。
   - **修復**：隔離 LLM Prompt 中的「實時網路搜尋補充參考資料」與「對話 Session Context」，明確規定搜尋結果不得當作用戶講過的話。
2. **[2026/07/27] 語音錯字修正（福建莆田 ➔ 浮沉浮沉）**：
   - **現象**：STT 將莆田辨識為「浮填」，LLM 糾錯寫成「浮沉浮沉」。
   - **修復**：升級模型至 `small`，改進 STT 糾錯 Prompt，加入常見地名、姓名防混淆邏輯，並啟動 `user_glossary` 自動學習。
3. **[2026/07/27] 雙 Session 請求與聲音疊加自言自語**：
   - **現象**：語音自動發送一次、底部修正又發送一次；麥克風收錄 AI 喇叭回音形成死循環。
   - **修復**：改為語音僅預覽不自動發送，加入 `isSpeaking` 麥克風互斥鎖與 `stopCurrentAudio()` 強制切斷。
4. **[2026/07/28] `cosine_similarity` NameError + 搜尋阻塞 event loop**：
   - **現象 A**：`app/server.py:147` 內外層 `for a, b in zip(...)` 變數 shadowing，外層 `zip(v1, b)` 的 `b` 在第一次迭代時尚未綁定，每次呼叫直接 `NameError`。**自部署以來 Google embedding 語意路由完全失效**，僅 regex fallback 在運作；正因如此 `cosine_similarity` 雖在線但無人察覺。
   - **現象 B**：`web_search` 內的 `DDGS().text(...)` 為同步 HTTP，在 async WebSocket handler 中直接呼叫會凍結整個 event loop。搜尋期間其他 client 連線 / 訊息都會被卡住。
   - **修復 A**：dot product 改為單層 `sum(a * b for a, b in zip(v1, v2))`，並以四組標準向量（identical / orthogonal / opposite / 45°）通過驗證。
   - **修復 B**：呼叫端改為 `await asyncio.to_thread(web_search, ...)`，丟到預設 thread pool 執行。
   - **Commit**：`50cb89b` (pushed to main)，GHCR image 已重 build（run #30315538961, 2m55s）。

### ⏳ 待持續觀測與後續驗證事項 (Next Actions):
- [ ] **長期個人化詞典準確度測試**：測試連續多天使用後，`user_glossary` 詞庫增量累積對同音異字（如莆田、阿胖山）自動校正的成功率。
- [ ] **Intel iGPU (OpenVINO / IPEX)Whisper 推理加速**：進一步測試將 `small` / `medium` Whisper 模型綁定至 N100 Intel GPU (RenderD128) 推理，減輕 CPU 負擔。
- [ ] **`is_semantic_search_intent` 同步呼叫**：內含 `get_google_embedding`（同步 urllib），目前沒包 thread，搜尋意圖判定時仍會輕微阻塞；可順手改為 `to_thread`。
- [ ] **STT / LLM / TTS 其餘同步阻塞呼叫**：`correct_stt_text`、`generate_cloned_tts`、`stt_model.transcribe` (line 578) 仍為同步執行；Whisper CPU 推論 1–3 秒為最大卡頓源，等真正感受到多 client 並發卡頓時再批次改 async。

---

## 🏠 維護與清理 (Housekeeping — 專案穩定後執行)

### GHCR Image Versions 清理計畫

**時機**：等專案穩定後（建議第一個正式 release / v1.0.0 階段）做一次「實驗性清理」。

**目前狀態**（2026-07-28）：25 個 image version 累積，1 個有 `latest` tag（k3s 在用），24 個 untagged 或 stale。

**清理步驟**（事後被雷過的標準做法）：

1. **打開**：https://github.com/kuniakil/cyber-girlfriend/pkgs/container/cyber-girlfriend/versions
2. **視覺確認 KEEP 清單**：
   - 目前有 `latest` tag 的那個（跑中 pod 在用）
   - 任何將來想保留的 explicit `v*.*.*` tag
3. **逐個砍**（不要批次）：
   - 點右邊 kebab menu → Delete version
   - **砍之前先把 digest 抄下來**（30 天內可從 Settings > Packages > Deleted > Restore 救回）
4. **砍一個、驗證一次**：
   - 砍完跑 `kubectl rollout restart deployment/voice-agent -n voice-agent`
   - 確認 pod 拉得到 image（沒有的話 30 天內 restore）
5. **預期結果**：
   - **順利**：以後知道怎麼清，**把這個程序記下來**
   - **失敗**：剛好把累積的「亂七八糟」都清掉，**順便做一個穩定版 image**，乾淨重來

**安全網**：
- GHCR 官方文件確認：**砍掉的 version 30 天內可 restore**
- 30 天過後就真的沒了，要回滾只能 `git checkout` 舊 commit + 重新 build

**為什麼不現在砍**：
- 還在頻繁 debug，隨時可能需要 rollback 到舊 image 測試
- 砍錯的後果在 debug 階段是不可接受的（會打斷正在進行的修復）
- 25 個 version 累積沒爆炸，GHCR 應該有某種 GC（雖然沒公開文件保證）

**觀察佐證 GHCR 有 GC**：累積 25 個 image version 從未被通知超量 → 大型 registry 不可能完全沒 GC。

**參考資料**：
- 官方文件：[Deleting and restoring a package](https://docs.github.com/en/packages/learn-github-packages/deleting-and-storing-a-package) — 30 天 restore window 條款出處
- 設計決策：見 commit `a092383` (workflow 改手動 trigger) 與 `d4c1dda` (deployment 改 `:latest`)

---

## 🔮 v2.0 待辦與升級規劃 (TODO for v2.0)

- [ ] **Wav2Lip / LivePortrait 3D 動態驅動**
  - 引入 `LivePortrait` 或 `Wav2Lip` 驅動器，實現講話時頭部自然傾斜、點頭與 3D 口型開合。
- [ ] **多硬體加速後端切換器 (Multi-Backend Hardware Selector)**
  - 提供設定選單：`CPU (Default)` / `NVIDIA CUDA` / `Intel OpenVINO` / `AMD ROCm` / `Apple Silicon MPS`。
- [ ] **多人設與自訂 LLM/TTS API 彈窗**
  - 前端 ⚙️ Settings 選單，支援切換 DeepSeek / Kimi / Ollama 或替換自訂語音 ID。
