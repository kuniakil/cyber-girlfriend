# 🧠 Intel GPU 加速啟用計畫 (Cyber Girlfriend Whisper STT)

**目標**：讓 Whisper STT 跑在 N100 iGPU (RenderD128) 上，比照 Immich ML 模式。
**當前狀態**：❌ **未啟用** — Docker image 內建的 GPU 路徑因缺套件 / 缺 GPU 透通，永遠 fallback 到 CPU faster-whisper。
**參考來源**：Immich ML Dockerfile + `pyproject.toml` (commit 2026-07-28 查證)
**底層技術**：ONNX Runtime + OpenVINO Execution Provider（**不是** `optimum-intel`）

---

## 🚨 重要：2026-07-28 計畫澄清紀錄

之前計畫有一處錯誤，現已修正：

| 之前說法 | 實際情況 |
|---|---|
| 「Immich 用 `optimum-intel[openvino]`」 | ❌ **錯**。Immich 完全不用 optimum 系。 |
| 「應該改用 `OVModelForSpeechSeq2Seq`」 | ❌ **錯**。那條是 `optimum-intel` 路徑，Immich 不用。 |
| 「要加 Level Zero runtime」 | ❌ **錯**。Immich 只用 OpenCL ICD，不裝 Level Zero。 |
| 「現有 `optimum[onnxruntime]` 為什麼 NG」 | ✅ **部分對**：方向對但細節錯。**真正原因是缺 `transformers`**。 |

**事實是**：
- Immich 用裸 `onnxruntime-openvino`（ONNX Runtime + OpenVINO backend）
- 你的現有程式碼用 `optimum.onnxruntime.ORTModelForSpeechSeq2Seq`（HuggingFace 包的 ONNX Runtime + OpenVINO）
- **兩者都走 ONNX Runtime + OpenVINO 路線**，差別只在有沒有 HuggingFace optimum 幫你做 ONNX export + pipeline 組裝
- 你走 HuggingFace 路徑**完全沒問題**，只是缺 `transformers` 套件

---

## 📌 進度追蹤表（任何 AI agent 接續前請先讀此表）

### Phase 0 — 診斷 (✅ 完成)

- [x] 確認 Dockerfile 已裝 Intel OpenCL ICD + IGC + libigdgmm12（`e90ac8c`）
- [x] 確認 server.py 用 `optimum.onnxruntime.ORTModelForSpeechSeq2Seq` 試圖載入 OpenVINO provider（`server.py:127-145`）
- [x] 確認 fallback 路徑永遠是 `faster-whisper` CPU int8（`server.py:149-150`）
- [x] 確認 docker-compose.yml **未**掛 `/dev/dri`、**未**加 `group_add: ["990"]`、**未**設 `WHISPER_DEVICE`
- [x] 確認 Dockerfile **未**裝 `transformers` → GPU 載入 100% ImportError
- [x] 確認 Dockerfile 用 `optimum[onnxruntime]`（跟 Immich 同路線，**不需改**）
- [x] 澄清：Immich 用裸 `onnxruntime-openvino`，不是 `optimum-intel`

### Phase 1 — Dockerfile 修正

- [ ] **1.1** 加裝 `transformers`（**真正缺少的唯一關鍵套件**）
- [ ] **1.2** 驗證 `huggingface-hub` 已安裝（optimum 應會帶進來；用 `pip show` 確認）
- [ ] **1.3** 驗證 `tokenizers` 已安裝（同上）
- [ ] **1.4** （可選，加強相容性）加裝 Immich 也裝的 `intel-igc-core-2_2.36.3` + `intel-igc-opencl-2_2.36.3` 新版，與現有 `1.0.17537.24` 並存
- [ ] **1.5** （可選）加裝 Immich 也裝的 `intel-opencl-icd-legacy1_24.35.30872.36-0_amd64.deb`
- [ ] **1.6** ~~加 Level Zero~~ → **取消**（Immich 也不用，N100 OpenCL ICD 已足）
- [ ] **1.7** 加 `ENV LIBVA_DRIVER_NAME=iHD`
- [ ] **1.8** 加 `ENV OPENVINO_LOG_LEVEL=1`（debug 用）

### Phase 2 — server.py 修正（**不需大改**，只補 logging + 例外分類）

- [ ] **2.1** 啟動時印出 ONNX Runtime 版本、可用 providers 清單、render group GID
- [ ] **2.2** 確認 `from optimum.onnxruntime import ORTModelForSpeechSeq2Seq` 這條 import 是對的（**保留**，不需要改成 `optimum.intel`）
- [ ] **2.3** 確認 `from transformers import AutoProcessor, pipeline` 這條 import 是對的（**保留**，裝好 transformers 後就會 work）
- [ ] **2.4** 把目前 `except Exception` 拆成明確分類：`ImportError`（套件缺）/ `RuntimeError`（driver/device 問題）/ 其他
- [ ] **2.5** fallback log 訊息明確標示 `→ Falling back to faster-whisper CPU int8 (no Intel GPU acceleration)` 與失敗原因
- [ ] **2.6** 新增 `WHISPER_DEVICE` env var 判斷：`auto` / `gpu` / `cpu`（auto = 試 GPU 失敗就 fallback；cpu = 強制 CPU）
- [ ] **2.7** 在 `from_pretrained(model_id, export=True)` 之前先檢查 `WHISPER_MODEL_SIZE in ["tiny", "base", "small", "medium", "large"]`，不支援的 size 直接 fallback 並 log

### Phase 3 — docker-compose.yml GPU 透通

- [ ] **3.1** 加 `devices: ["/dev/dri:/dev/dri"]`
- [ ] **3.2** 加 `group_add: ["990"]`
- [ ] **3.3** 加 `environment: WHISPER_DEVICE=auto`
- [ ] **3.4** 加 `environment: LIBVA_DRIVER_NAME=iHD`
- [ ] **3.5** （可選）改用明確 image tag 而非 `:latest`，方便 rollback

### Phase 4 — 本地 build + 煙霧測試

- [ ] **4.1** `docker build -t cyber-girlfriend:igpu-test .`
- [ ] **4.2** 進 container 跑 `clinfo | head -20` → 確認能看到 Intel GPU platform
- [ ] **4.3** 進 container 跑 `python3 -c "import onnxruntime as ort; print(ort.get_available_providers())"` → 應輸出 `['OpenVINOExecutionProvider', 'CPUExecutionProvider']`
- [ ] **4.4** 進 container 跑 STT pipeline load 測試：
  ```bash
  python3 -c "
  from optimum.onnxruntime import ORTModelForSpeechSeq2Seq
  from transformers import AutoProcessor, pipeline
  m = ORTModelForSpeechSeq2Seq.from_pretrained(
      'openai/whisper-small', export=True,
      provider='OpenVINOExecutionProvider',
      provider_options={'device_type': 'GPU_FP16'}
  )
  print('GPU load OK')
  "
  ```
- [ ] **4.5** 確認 log 中出現 `ONNXRuntime Intel GPU (OpenVINOExecutionProvider) Whisper pipeline successfully loaded!`

### Phase 5 — 部署到 k3s

- [ ] **5.1** 確認 Phase 1~4 全部 ✓，commit + push
- [ ] **5.2** 等 GHCR workflow 完成（手動 `workflow_dispatch`）
- [ ] **5.3** 更新 k3s deployment image tag
- [ ] **5.4** `kubectl logs -n voice-agent ... | grep -iE 'openvino|provider|gpu'` → 確認 OpenVINO GPU 載入成功
- [ ] **5.5** 對 `http://localhost:8765/api/system_status` 觀察 `gpu_freq` 欄位 → STT 推理時應有明顯跳動

---

## 🔧 技術細節參考

### 為什麼 `optimum[onnxruntime]` 路線其實是對的？

**Immich ML Python 套件對照表**（從 `pyproject.toml` 查證）：

| Immich ML 用 | 你的現況 | 用途 |
|---|---|---|
| `onnxruntime-openvino>=1.24.1,<2` | ✅ 已有 | **同一條路**：ONNX Runtime + OpenVINO backend |
| `huggingface-hub>=1.0,<2.0` | 應該有（optimum 帶） | 下載 HF 模型 |
| `tokenizers>=0.15.0,<1.0` | 應該有（optimum 帶） | Whisper tokenizer |
| `optimum-intel[openvino]` | ❌ **不需要** | Immich 也不用 |
| `optimum[onnxruntime]` | ✅ 已有 | HuggingFace 包的 ONNX Runtime + pipeline 組裝 |
| `transformers` | ❌ **缺這個** | 提供 `AutoProcessor`（feature extractor + tokenizer） |

**結論**：你已經走在 Immich 同條路上（ONNX Runtime + OpenVINO backend），缺的只有 **`transformers`**。

### 為什麼當初 OpenVINO 直連路徑走不通？

你提到「OpenVINO 的話資源並不完整」。這跟實際情況一致：
- `optimum.intel.OVModelForSpeechSeq2Seq`（OpenVINO 直連）需要 Whisper ONNX → OpenVINO IR 的轉換
- HuggingFace 上有現成的 `openai/whisper-small` ONNX model（例如 `Xenova/whisper-small`），但**只有 ONNX 格式，沒有 OpenVINO IR**
- 要從 ONNX 轉 OpenVINO IR 需要額外的 conversion tool，文件不完整
- **ONNX Runtime + OpenVINO Execution Provider 路徑可以直接吃 ONNX 模型**，繞過轉 IR 這步

所以你的技術選擇（`optimum.onnxruntime` 而不是 `optimum.intel`）是對的。

### Dockerfile driver 安裝對照

| Immich 裝的（從 GitHub release） | 你的現況 | 備註 |
|---|---|---|
| `intel-igc-core-2_2.36.3+21719_amd64.deb` | ❌ 缺（可選加） | Immich 雙裝，舊版也留 |
| `intel-igc-opencl-2_2.36.3+21719_amd64.deb` | ❌ 缺（可選加） | 同上 |
| `intel-opencl-icd_26.22.38646.4-0_amd64.deb` | ✅ 已有 | — |
| `intel-igc-core_1.0.17537.24_amd64.deb` | ✅ 已有 | — |
| `intel-igc-opencl_1.0.17537.24_amd64.deb` | ✅ 已有 | — |
| `intel-opencl-icd-legacy1_24.35.30872.36-0_amd64.deb` | ❌ 缺（可選加） | 為舊 GPU fallback |
| `libigdgmm12_22.10.0_amd64.deb` | ✅ 已有 | — |
| `level-zero` | ❌ 不裝 | Immich 也沒裝（OpenCL 已足） |

### docker-compose GPU 透通（Immich 模式）

```yaml
services:
  cyber-girlfriend:
    image: ghcr.io/kuniakil/cyber-girlfriend:igpu-test
    devices:
      - /dev/dri:/dev/dri
    group_add:
      - "990"  # render group
    environment:
      - WHISPER_DEVICE=auto
      - LIBVA_DRIVER_NAME=iHD
      - MINIMAX_API_KEY=...
```

---

## 🔄 中斷接續指引（給 Antigravity / 任何 AI agent）

> **如果你（AI agent）讀到這份文件，請遵守以下規則：**

1. **先讀這個檔案**：永遠先讀 `INTEL_GPU_PLAN.md` 確認進度
2. **從第一個未勾選的 task 接續**：不要重新做已完成的 phase
3. **完成一個 task 就把 `[ ]` 改成 `[x]`**：保持這份文件是 single source of truth
4. **不要同時改太多檔案**：每完成一個 phase 才 commit
5. **每個 phase 完成後**：跑 Phase 4 的對應煙霧測試，再進入下一 phase
6. **遇到 import / runtime 錯誤**：把錯誤訊息貼回這份文件的「🐛 已知問題」段落，再決定下一步

---

## 🐛 已知問題（debug 用）

<!-- AI agent 請把遇到的錯誤訊息記在這裡 -->

（目前無）

---

## 📚 參考連結

- Immich ML `pyproject.toml`: https://github.com/immich-app/immich/blob/main/machine-learning/pyproject.toml
- Immich ML `Dockerfile`: https://github.com/immich-app/immich/blob/main/machine-learning/Dockerfile
- ONNX Runtime OpenVINO Execution Provider: https://onnxruntime.ai/docs/execution-providers/OpenVINO-ExecutionProvider.html
- `optimum.onnxruntime` 文件: https://huggingface.co/docs/optimum/main/en/onnxruntime/overview
- HuggingFace Whisper ONNX 模型: https://huggingface.co/Xenova/whisper-small
