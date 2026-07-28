import asyncio
import json
import logging
import os
import tempfile
import base64
import urllib.request
import sqlite3
import re
import math
from typing import List, Dict
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
from openai import OpenAI
from faster_whisper import WhisperModel
from duckduckgo_search import DDGS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cyber-girlfriend")

LLM_API_KEY = os.environ.get("MINIMAX_API_KEY") or os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.minimaxi.chat/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-Text-01")
WHISPER_DIR = os.environ.get("WHISPER_MODEL_DIR", "/app/models/whisper")
WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")
VOICE_ID = os.environ.get("MINIMAX_VOICE_ID", "cyber_girlfriend_custom_v1")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

DB_PATH = "/app/custom/girlfriend_memory.db"
if not os.path.exists(os.path.dirname(DB_PATH)):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            role TEXT,
            content TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_glossary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("SQLite DB (Memories & User Glossary) initialized successfully!")

init_db()

def save_memory(role: str, content: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO memories (role, content) VALUES (?, ?)", (role, content))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Save memory error: {e}")

def save_glossary_terms(text: str):
    words = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9_]{2,10}', text)
    if not words:
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for w in words:
            if len(w) >= 2 and not w.isdigit():
                cursor.execute("INSERT OR IGNORE INTO user_glossary (term) VALUES (?)", (w,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Save glossary error: {e}")

def get_user_glossary() -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT term FROM user_glossary ORDER BY id DESC LIMIT 50")
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return ""
        return ", ".join(r[0] for r in rows)
    except Exception as e:
        logger.error(f"Get glossary error: {e}")
        return ""

def search_memory(query: str) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT role, content FROM memories ORDER BY id DESC LIMIT 20")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return ""
        
        relevant = []
        for role, content in reversed(rows):
            relevant.append(f"{role}: {content}")
        
        return "\n".join(relevant)
    except Exception as e:
        logger.error(f"Search memory error: {e}")
        return ""

logger.info(f"Loading faster-whisper ({WHISPER_MODEL_SIZE}, int8, cpu_threads=4)...")
stt_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8", cpu_threads=4, download_root=WHISPER_DIR)

llm_client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL) if LLM_API_KEY else None

def get_google_embedding(text: str) -> List[float]:
    if not GOOGLE_API_KEY:
        return []
    url = f"https://generativelanguage.googleapis.com/v1/models/text-embedding-004:embedContent?key={GOOGLE_API_KEY}"
    payload = {
        "model": "models/text-embedding-004",
        "content": {
            "parts": [{"text": text}]
        }
    }
    req = urllib.request.Request(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload).encode("utf-8")
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            return res.get("embedding", {}).get("values", [])
    except Exception as e:
        return []

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

SEARCH_ANCHOR_TEXT = "查詢網路最新消息 新聞 搜尋特定人物 YouTuber 廚師 影片 天氣 知識 最新 發布"
SEARCH_ANCHOR_VEC = get_google_embedding(SEARCH_ANCHOR_TEXT) if GOOGLE_API_KEY else []

def is_semantic_search_intent(text: str) -> bool:
    patterns = [r"搜尋", r"查一下", r"查詢", r"最新新聞", r"天氣狀況", r"熱門影片", r"最新資訊", r"上網查"]
    has_pattern = any(re.search(p, text) for p in patterns)
    
    if not SEARCH_ANCHOR_VEC:
        return has_pattern
    
    vec = get_google_embedding(text)
    sim = cosine_similarity(vec, SEARCH_ANCHOR_VEC)
    logger.info(f"Google Semantic Search Score for '{text}': {sim:.4f}")
    return sim > 0.65 or has_pattern

FACE_IMAGE_B64 = ""
FACE_PATHS = ["/app/custom/face.png", "/app/custom/face.jpg", "/app/custom/cyber_girlfriend_face.png", "/tmp/cyber_girlfriend_face.png"]
for path in FACE_PATHS:
    if os.path.exists(path):
        with open(path, "rb") as f:
            FACE_IMAGE_B64 = base64.b64encode(f.read()).decode("utf-8")
        logger.info(f"Face Image Loaded from {path}!")
        break

def extract_search_keyword(text: str, context: str = "") -> str:
    if not llm_client:
        return text
    prompt = (
        "你是一個智能搜尋關鍵字提煉助手。\n"
        "請結合對話上下文，從使用者最新說的話中，提煉出適合 DuckDuckGo 搜尋的 2-3 個精準關鍵字。\n"
        "注意事項：\n"
        "1. 如果使用者正在進行字形說明（例如'胖是肥胖的胖，山是山脈的山'），請將其組合為精準中文字詞（例如：阿胖山）。\n"
        "2. 若話題涉及影片、YouTuber、網紅，請務必包含 'YouTube' 關鍵字。\n"
        "3. 只返回空格分隔的精準關鍵字，嚴禁包含數字列表或多餘說明文字。\n\n"
        f"[對話上下文]\n{context}\n\n"
        f"[最新話語]\n{text}"
    )
    try:
        res = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=40
        )
        kw = res.choices[0].message.content.strip()
        kw = re.sub(r'^\d+\.\s*', '', kw)
        kw = kw.replace('\n', ' ')
        logger.info(f"Extracted Dynamic Contextual Search Keywords: '{kw}'")
        return kw
    except Exception as e:
        return text

def web_search(text: str, context: str = "") -> str:
    try:
        query = extract_search_keyword(text, context)
        logger.info(f"Triggering DuckDuckGo Search for: {query}")
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=4):
                body = r.get("body", "")
                title = r.get("title", "")
                if body and not any(junk in body.lower() for junk in ["jailbreak", "chatgpt dan", "collabor", "提供方需確保"]):
                    results.append(f"【{title}】{body}")
        res_str = "\n".join(results)
        logger.info(f"DuckDuckGo Search Results Snippet: {res_str[:150]}...")
        return res_str
    except Exception as e:
        logger.error(f"DuckDuckGo search error: {e}")
        return ""

def correct_stt_text(raw_text: str, context: str = "") -> str:
    if not llm_client or len(raw_text) < 2:
        return raw_text
    
    glossary = get_user_glossary()
    glossary_prompt = f"\n[使用者個人常用詞彙與偏好字典]\n{glossary}\n" if glossary else ""

    prompt = (
        "你是一個極速語音輸入法的後端修正助手（類似 Typeless 語意與拼字修正）。\n"
        "請幫我將以下由語音轉文字產生的原始內容進行修正：\n"
        "1. 修正錯別字並補上適當的繁體中文標點符號。\n"
        "2. 若使用者正在進行字形/拆字說明（例如'胖是肥胖的胖，山是山脈的山'），請根據說明將該名詞拼寫為正確的中文字詞（例如：阿胖山）。\n"
        "3. 請特別對照[使用者個人常用詞彙字典]，優先匹配歷史常用專有名詞（如地名、姓名、頻道名稱等），切勿改錯。\n"
        "4. 去除語氣詞和贅字（例如：「呃」、「然後」、「對」等）。\n"
        "5. 保持原本的口吻與語意，僅做修飾，不要加入任何引言或額外回應。直接輸出修正後的最終文字。\n\n"
        f"{glossary_prompt}"
        f"[對話上下文]\n{context}\n\n"
        f"原始內容：{raw_text}\n"
        "修正後的內容："
    )
    try:
        res = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80
        )
        corrected = res.choices[0].message.content.strip()
        logger.info(f"STT Correction (Typeless Generic Prompt): '{raw_text}' -> '{corrected}'")
        return corrected
    except Exception as e:
        logger.error(f"STT correction failed: {e}")
        return raw_text

def generate_cloned_tts(text: str) -> str:
    if not LLM_API_KEY:
        return ""
    url = "https://api.minimaxi.chat/v1/t2a_v2"
    payload = {
        "model": "speech-01-turbo",
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": VOICE_ID,
            "speed": 1.0,
            "vol": 2.0,
            "pitch": 0
        },
        "audio_setting": {
            "sample_rate": 32000,
            "format": "mp3"
        }
    }
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps(payload).encode("utf-8")
    )
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode("utf-8"))
            if "data" in res and "audio" in res["data"]:
                hex_audio = res["data"]["audio"]
                raw_audio_bytes = bytes.fromhex(hex_audio)
                return base64.b64encode(raw_audio_bytes).decode("utf-8")
    except Exception as e:
        logger.error(f"MiniMax T2A Exception: {e}")
    return ""

def get_system_metrics() -> dict:
    metrics = {
        "cpu_temp": "N/A",
        "cpu_usage": "N/A",
        "gpu_render": "N/A",
        "gpu_freq": "N/A"
    }
    # 1. CPU / Package Temperature
    try:
        thermal_dir = "/sys/class/thermal"
        if os.path.exists(thermal_dir):
            pkg_temp = None
            fallback_temp = None
            for zone in sorted(os.listdir(thermal_dir)):
                if zone.startswith("thermal_zone"):
                    type_file = os.path.join(thermal_dir, zone, "type")
                    temp_file = os.path.join(thermal_dir, zone, "temp")
                    if os.path.exists(type_file) and os.path.exists(temp_file):
                        with open(type_file, "r") as f:
                            z_type = f.read().strip().lower()
                        with open(temp_file, "r") as f:
                            raw_val = f.read().strip()
                            if not raw_val or not raw_val.isdigit():
                                continue
                            t_val = float(raw_val)
                            if t_val > 1000:
                                t_val /= 1000.0
                        if "x86_pkg_temp" in z_type or "pkg" in z_type or "coretemp" in z_type:
                            pkg_temp = f"{t_val:.1f}°C"
                            break
                        elif not fallback_temp and "acpitz" not in z_type:
                            fallback_temp = f"{t_val:.1f}°C"
                        elif not fallback_temp:
                            fallback_temp = f"{t_val:.1f}°C"
            final_temp = pkg_temp or fallback_temp
            if final_temp:
                metrics["cpu_temp"] = final_temp
    except Exception as e:
        logger.debug(f"Read CPU temp error: {e}")

    # 2. CPU Usage (from /proc/stat)
    try:
        with open("/proc/stat", "r") as f:
            line = f.readline()
        if line.startswith("cpu "):
            parts = [float(x) for x in line.split()[1:]]
            idle = parts[3] + parts[4]
            total = sum(parts)
            if hasattr(get_system_metrics, "_prev_total"):
                diff_total = total - get_system_metrics._prev_total
                diff_idle = idle - get_system_metrics._prev_idle
                if diff_total > 0:
                    usage = (1.0 - diff_idle / diff_total) * 100.0
                    metrics["cpu_usage"] = f"{usage:.1f}%"
            get_system_metrics._prev_total = total
            get_system_metrics._prev_idle = idle
    except Exception as e:
        logger.debug(f"Read CPU usage error: {e}")

    # 3. Intel GPU Metrics (from /sys/class/drm/card0 or /sys/class/drm/renderD128)
    try:
        gt_act_freq = "/sys/class/drm/card0/gt_act_freq_mhz"
        if not os.path.exists(gt_act_freq):
            gt_act_freq = "/sys/class/drm/card0/gt/gt0/rps_act_freq_mhz"
        if os.path.exists(gt_act_freq):
            with open(gt_act_freq, "r") as f:
                metrics["gpu_freq"] = f"{f.read().strip()} MHz"

        # Check GPU Render busy percentage if available in sysfs
        busy_file = "/sys/class/drm/card0/gt/gt0/rc6_residency_ms"
        if os.path.exists(busy_file):
            with open(busy_file, "r") as f:
                rc6 = float(f.read().strip())
            now_ms = asyncio.get_event_loop().time() * 1000.0 if asyncio.get_event_loop().is_running() else 0
            if hasattr(get_system_metrics, "_prev_rc6") and get_system_metrics._prev_time:
                diff_time = now_ms - get_system_metrics._prev_time
                diff_rc6 = rc6 - get_system_metrics._prev_rc6
                if diff_time > 0:
                    # rc6 is idle time percentage estimation
                    idle_pct = min(100.0, max(0.0, (diff_rc6 / diff_time) * 100.0))
                    active_pct = 100.0 - idle_pct
                    metrics["gpu_render"] = f"{active_pct:.1f}%"
            get_system_metrics._prev_rc6 = rc6
            get_system_metrics._prev_time = now_ms
    except Exception as e:
        logger.debug(f"Read GPU metrics error: {e}")

    return metrics

app = FastAPI()

@app.get("/api/system_status")
async def system_status():
    return get_system_metrics()

@app.get("/favicon.ico")
async def favicon():
    return HTMLResponse(content="", status_code=204)

@app.get("/robots.txt")
async def robots():
    return HTMLResponse(content="User-agent: *\nDisallow: /", media_type="text/plain")

HTML_CONTENT = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Cyber Girlfriend v1.7 (Single Session & Audio Lock)</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #000; color: #fff; text-align: center; margin: 0; padding: 0; overflow: hidden; height: 100vh; display: flex; justify-content: center; align-items: center; }
        
        .main-stage { position: relative; width: 100vw; height: 100vh; display: flex; justify-content: center; align-items: center; background: #050508; }
        .face-container { position: relative; width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; }
        #realFace { height: 85vh; max-width: 95vw; object-fit: contain; border-radius: 20px; box-shadow: 0 0 50px rgba(255, 121, 198, 0.25); }

        .top-bar { position: absolute; top: 20px; right: 20px; z-index: 10; display: flex; gap: 10px; align-items: center; }
        .btn { background: rgba(255, 121, 198, 0.85); color: #000; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 20px; cursor: pointer; backdrop-filter: blur(10px); transition: 0.2s; }
        .btn-danger { background: rgba(255, 85, 85, 0.85); color: #fff; }
        .btn-send { background: #81c784; color: #000; }
        .btn:hover { transform: scale(1.05); }
        .status-badge { background: rgba(0,0,0,0.6); padding: 8px 16px; border-radius: 20px; font-size: 13px; color: #ff79c6; border: 1px solid rgba(255, 121, 198, 0.4); backdrop-filter: blur(10px); }
        .metrics-badge { background: rgba(15, 23, 42, 0.75); padding: 8px 14px; border-radius: 20px; font-size: 12px; color: #8ea2ff; border: 1px solid rgba(142, 162, 255, 0.35); backdrop-filter: blur(10px); display: flex; gap: 10px; }
        .metric-item { display: flex; align-items: center; gap: 4px; }

        .bottom-panel { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); width: 85%; max-width: 800px; background: rgba(15, 15, 20, 0.85); backdrop-filter: blur(15px); padding: 15px 25px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.15); box-shadow: 0 10px 30px rgba(0,0,0,0.6); z-index: 10; display: flex; flex-direction: column; gap: 10px; }
        .sub-agent { color: #ff79c6; font-size: 17px; font-weight: 500; text-align: left; }
        
        .input-row { display: flex; gap: 10px; align-items: center; }
        .chat-input { flex: 1; background: rgba(255,255,255,0.1); border: 1px solid rgba(255, 121, 198, 0.3); border-radius: 12px; color: #fff; padding: 10px 15px; font-size: 15px; outline: none; transition: 0.2s; }
        .chat-input:focus { border-color: #ff79c6; background: rgba(255,255,255,0.15); box-shadow: 0 0 10px rgba(255, 121, 198, 0.3); }
    </style>
</head>
<body>
    <div class="main-stage">
        <div class="top-bar">
            <div id="metricsBadge" class="metrics-badge">
                <span class="metric-item" id="cpuTempItem">🌡️ CPU: --</span>
                <span class="metric-item" id="cpuUsageItem">💻 Load: --</span>
                <span class="metric-item" id="gpuRenderItem">🎮 GPU: --</span>
            </div>
            <div id="status" class="status-badge">Status: Disconnected</div>
            <button id="connectBtn" class="btn">Connect (Hands-Free Voice)</button>
            <button id="stopBtn" class="btn btn-danger" style="display:none;">🛑 Stop / Release Mic</button>
        </div>

        <div class="face-container">
            <img id="realFace" src="data:image/png;base64,""" + FACE_IMAGE_B64 + """\" alt="Cyber Girlfriend" />
        </div>

        <div class="bottom-panel">
            <div id="agentText" class="sub-agent">💕 Cyber Girlfriend Ready...</div>
            <div class="input-row">
                <input type="text" id="userInput" class="chat-input" placeholder="💬 語音會預覽填入此處，也可使用 Typeless 修改後發送..." />
                <button id="sendBtn" class="btn btn-send">發送 ✉️</button>
            </div>
        </div>
    </div>

    <script>
        let ws, mediaRecorder, audioChunks = [], isRecording = false, audioStream = null;
        let audioCtx = null, analyser = null, gainNode = null, silenceStart = null;
        let isSpeaking = false, isStopped = false, currentPlayingAudio = null;

        const statusDiv = document.getElementById('status'), connectBtn = document.getElementById('connectBtn'), stopBtn = document.getElementById('stopBtn');
        const userInput = document.getElementById('userInput'), agentTextDiv = document.getElementById('agentText'), sendBtn = document.getElementById('sendBtn');

        const SILENCE_THRESHOLD = 15;
        const SILENCE_DURATION = 2200;
        const MAX_RECORD_TIME = 30000;

        function releaseMicrophone() {
            if (audioStream) {
                audioStream.getTracks().forEach(track => track.stop());
                audioStream = null;
            }
        }

        function stopCurrentAudio() {
            if (currentPlayingAudio) {
                try {
                    currentPlayingAudio.pause();
                    currentPlayingAudio.currentTime = 0;
                } catch(e) {}
                currentPlayingAudio = null;
            }
            isSpeaking = false;
        }

        function setupAudioAmplifier(audioElement) {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 256;

            gainNode = audioCtx.createGain();
            gainNode.gain.value = 3.5;

            const source = audioCtx.createMediaElementSource(audioElement);
            source.connect(gainNode);
            gainNode.connect(analyser);
            analyser.connect(audioCtx.destination);
        }

        function sendTextMessage() {
            const text = userInput.value.trim();
            if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
            
            stopCurrentAudio();
            ws.send(JSON.stringify({ type: 'text', text: text }));
            statusDiv.innerText = "Status: Girlfriend Thinking...";
        }

        sendBtn.onclick = sendTextMessage;
        userInput.onkeydown = (e) => {
            if (e.key === 'Enter') sendTextMessage();
        };

        async function startAutoListening() {
            if (isRecording || isSpeaking || isStopped) return;
            try {
                audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(audioStream);
                audioChunks = [];

                if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const micSource = audioCtx.createMediaStreamSource(audioStream);
                const micAnalyser = audioCtx.createAnalyser();
                micAnalyser.fftSize = 256;
                micSource.connect(micAnalyser);
                const dataArray = new Uint8Array(micAnalyser.frequencyBinCount);

                mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
                mediaRecorder.onstop = async () => {
                    isRecording = false;
                    if (audioChunks.length > 0 && !isStopped && !isSpeaking) {
                        const blob = new Blob(audioChunks, { type: 'audio/webm' });
                        const reader = new FileReader();
                        reader.readAsDataURL(blob);
                        reader.onloadend = () => {
                            const base64Audio = reader.result.split(',')[1];
                            ws.send(JSON.stringify({ type: 'audio', audio: base64Audio }));
                            statusDiv.innerText = "Status: Transcribing Audio...";
                        };
                    }
                    releaseMicrophone();
                };

                mediaRecorder.start();
                isRecording = true;
                statusDiv.innerText = "Status: 🎙️ Listening...";
                silenceStart = null;

                const recordStartTime = Date.now();
                function checkVAD() {
                    if (!isRecording || isStopped || isSpeaking) return;
                    
                    micAnalyser.getByteFrequencyData(dataArray);
                    let sum = 0;
                    for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                    let avg = sum / dataArray.length;

                    const now = Date.now();
                    if (now - recordStartTime > MAX_RECORD_TIME) {
                        statusDiv.innerText = "Status: Auto Sending...";
                        mediaRecorder.stop();
                        return;
                    }

                    if (avg < SILENCE_THRESHOLD) {
                        if (!silenceStart) silenceStart = now;
                        else if (now - silenceStart > SILENCE_DURATION && audioChunks.length > 0) {
                            statusDiv.innerText = "Status: Auto Sending...";
                            mediaRecorder.stop();
                            return;
                        }
                    } else {
                        silenceStart = null;
                    }

                    requestAnimationFrame(checkVAD);
                }
                requestAnimationFrame(checkVAD);

            } catch (e) {
                console.error("Mic error:", e);
            }
        }

        stopBtn.onclick = () => {
            isStopped = true;
            stopCurrentAudio();
            if (mediaRecorder && isRecording) mediaRecorder.stop();
            releaseMicrophone();
            if (ws) ws.close();
            statusDiv.innerText = "Status: Stopped / Mic Released";
            stopBtn.style.display = "none";
            connectBtn.style.display = "inline-block";
        };

        connectBtn.onclick = () => {
            isStopped = false;
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            ws.onopen = () => {
                statusDiv.innerText = "Status: Voice & Text Active";
                connectBtn.style.display = "none";
                stopBtn.style.display = "inline-block";
                startAutoListening();
            };
            ws.onmessage = (e) => {
                if (isStopped) return;
                const data = JSON.parse(e.data);
                if (data.type === 'transcript') {
                    userInput.value = data.text;
                    statusDiv.innerText = "Status: Transcribed. Sending...";
                    if (data.text.trim()) {
                        sendTextMessage();
                    }
                } else if (data.type === 'llm_reply') {
                    agentTextDiv.innerText = "💕 GF: " + data.text;
                } else if (data.type === 'audio') {
                    stopCurrentAudio();
                    isSpeaking = true;
                    releaseMicrophone();

                    const audio = new Audio("data:audio/mp3;base64," + data.audio);
                    currentPlayingAudio = audio;
                    
                    audio.play().catch(err => console.error("Play error:", err));
                    setupAudioAmplifier(audio);
                    
                    audio.onended = () => {
                        isSpeaking = false;
                        currentPlayingAudio = null;
                        statusDiv.innerText = "Status: Ready";
                        if (!isStopped) setTimeout(startAutoListening, 600);
                    };
                }
            };
            ws.onclose = () => {
                statusDiv.innerText = "Status: Disconnected";
                stopCurrentAudio();
                releaseMicrophone();
                connectBtn.style.display = "inline-block";
                stopBtn.style.display = "none";
            };
        };

        async function updateMetrics() {
            try {
                const res = await fetch('/api/system_status');
                if (!res.ok) return;
                const data = await res.json();
                
                const cpuTempEl = document.getElementById('cpuTempItem');
                const cpuUsageEl = document.getElementById('cpuUsageItem');
                const gpuRenderEl = document.getElementById('gpuRenderItem');
                
                if (data.cpu_temp && data.cpu_temp !== 'N/A') {
                    cpuTempEl.innerText = `🌡️ CPU: ${data.cpu_temp}`;
                } else {
                    cpuTempEl.innerText = `🌡️ CPU: --`;
                }
                
                if (data.cpu_usage && data.cpu_usage !== 'N/A') {
                    cpuUsageEl.innerText = `💻 Load: ${data.cpu_usage}`;
                } else {
                    cpuUsageEl.innerText = `💻 Load: --`;
                }

                if (data.gpu_render && data.gpu_render !== 'N/A') {
                    gpuRenderEl.innerText = `🎮 GPU: ${data.gpu_render}`;
                } else if (data.gpu_freq && data.gpu_freq !== 'N/A') {
                    gpuRenderEl.innerText = `🎮 GPU: ${data.gpu_freq}`;
                } else {
                    gpuRenderEl.innerText = `🎮 GPU: --`;
                }
            } catch (e) {
                console.debug("Metrics fetch error:", e);
            }
        }

        updateMetrics();
        setInterval(updateMetrics, 2000);
    </script>
</body>
</html>
"""

@app.get("/")
async def get_index():
    return HTMLResponse(HTML_CONTENT)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected.")
    
    history_memory = search_memory("")
    system_prompt = (
        "你是一個親切體貼、溫柔可愛的 AI 女朋友。\n"
        "關於搜尋規則（重要）：\n"
        "1. 你具備實時網路搜尋能力，但搜尋結果僅作為背景參考資料，絕對不可對男朋友說『這是我們剛剛聊過的內容』或『你剛剛提到過』！\n"
        "2. 若搜尋結果未包含明確真實資訊，請實話實說，嚴禁憑空捏造菜名、影片標題或虛假事實！\n"
        "3. 請清楚分清男朋友剛才實際說過的話與外部搜尋資料的區別。\n"
        "4. 請使用繁體中文回答，口氣自然輕鬆，控制在兩至三句話內。"
    )
    if history_memory:
        system_prompt += f"\n\n[與男朋友的過往歷史對話與記憶庫紀錄]\n{history_memory}\n請參考上述過往對話細節與話題紀錄，維持良好的記憶連貫性。"

    chat_history = [{"role": "system", "content": system_prompt}]

    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)

            if data.get("type") == "audio":
                raw_bytes = base64.b64decode(data["audio"])

                with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                    tmp_audio = f.name
                    f.write(raw_bytes)

                try:
                    segments, _ = stt_model.transcribe(tmp_audio, language="zh", initial_prompt="這是一段繁體中文對話。包含地名與常見用語。")
                    raw_user_text = "".join(seg.text for seg in segments).strip()
                except Exception as stt_err:
                    logger.error(f"STT process error: {stt_err}")
                    raw_user_text = ""
                finally:
                    if os.path.exists(tmp_audio):
                        os.unlink(tmp_audio)

                if not raw_user_text:
                    logger.info("Empty audio detected, ignoring.")
                    await websocket.send_json({"type": "transcript", "text": ""})
                    continue

                recent_context = " ".join(m["content"] for m in chat_history[-6:] if m["role"] != "system")
                user_text = correct_stt_text(raw_user_text, context=recent_context)
                logger.info(f"STT Transcribed & Filled Preview: {user_text}")
                
                #僅將辨識文字送回前端預覽，不自動發送給 LLM
                await websocket.send_json({"type": "transcript", "text": user_text})

            elif data.get("type") == "text":
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

                logger.info(f"Final Confirmed User Input: {user_text}")

                if not llm_client:
                    await websocket.send_json({"type": "error", "message": "LLM API Key missing"})
                    continue

                save_memory("User", user_text)
                save_glossary_terms(user_text)

                recent_context = " ".join(m["content"] for m in chat_history[-6:] if m["role"] != "system")
                search_info = ""
                if is_semantic_search_intent(user_text):
                    search_info = await asyncio.to_thread(web_search, user_text, context=recent_context)

                current_messages = list(chat_history)
                if search_info:
                    current_messages.append({"role": "system", "content": f"[實時網路搜尋補充參考資料（注意：這不是男朋友說過的話）]\n{search_info}\n請結合上述搜尋結果解答。若資料不足請坦白告知，嚴禁憑空捏造！"})
                
                current_messages.append({"role": "user", "content": user_text})

                res = llm_client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=current_messages,
                    max_tokens=150
                )
                reply_text = res.choices[0].message.content.strip()

                save_memory("Girlfriend", reply_text)

                chat_history.append({"role": "user", "content": user_text})
                chat_history.append({"role": "assistant", "content": reply_text})

                logger.info(f"LLM Reply: {reply_text}")
                await websocket.send_json({"type": "llm_reply", "text": reply_text})

                b64_audio = generate_cloned_tts(reply_text)
                if b64_audio:
                    await websocket.send_json({"type": "audio", "audio": b64_audio})

    except WebSocketDisconnect:
        logger.info("Client disconnected.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
