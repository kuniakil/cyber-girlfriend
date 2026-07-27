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
    conn.commit()
    conn.close()
    logger.info("SQLite Long-Term Memory DB initialized successfully!")

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

def search_memory(query: str) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT role, content FROM memories ORDER BY id DESC LIMIT 15")
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

logger.info(f"Loading faster-whisper (base, int8)...")
stt_model = WhisperModel("base", device="cpu", compute_type="int8", download_root=WHISPER_DIR)

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

SEARCH_ANCHOR_TEXT = "查詢網路最新消息 新聞 搜尋特定人物 YouTuber 廚師 影片 天氣 知識 最新"
SEARCH_ANCHOR_VEC = get_google_embedding(SEARCH_ANCHOR_TEXT) if GOOGLE_API_KEY else []

def is_semantic_search_intent(text: str) -> bool:
    patterns = [r"搜尋", r"查一下", r"查詢", r"最新", r"新聞", r"天氣", r"影片", r"熱門", r"網紅", r"是誰", r"什麼是", r"知道.*嗎", r"聽過.*嗎"]
    has_pattern = any(re.search(p, text) for p in patterns)
    
    if not SEARCH_ANCHOR_VEC:
        return has_pattern
    
    vec = get_google_embedding(text)
    sim = cosine_similarity(vec, SEARCH_ANCHOR_VEC)
    logger.info(f"Google Semantic Search Score for '{text}': {sim:.4f}")
    return sim > 0.45 or has_pattern

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
    prompt = f"請結合對話上下文，從男朋友最新說的話中，提煉出適合 DuckDuckGo 搜尋的 2-3 個精準關鍵字。如果句子中有代詞（如'他'、'這個'），請根據上下文替換為具體人名或主體。只返回空格分隔的關鍵字（例如: '王剛 最新 菜色 影片'），嚴禁包含數字列表或多餘說明：\n[對話上下文]\n{context}\n[最新一句話]\n{text}"
    try:
        res = llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=30
        )
        kw = res.choices[0].message.content.strip()
        kw = re.sub(r'^\d+\.\s*', '', kw)
        kw = kw.replace('\n', ' ')
        logger.info(f"Extracted Contextual Search Keywords: '{kw}'")
        return kw
    except Exception as e:
        return text

def web_search(text: str, context: str = "") -> str:
    try:
        query = extract_search_keyword(text, context)
        logger.info(f"Triggering DuckDuckGo Search for: {query}")
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=3):
                body = r.get("body", "")
                if body:
                    results.append(body)
        res_str = "\n".join(results)
        logger.info(f"DuckDuckGo Search Results Snippet: {res_str[:120]}...")
        return res_str
    except Exception as e:
        logger.error(f"DuckDuckGo search error: {e}")
        return ""

# 移植自 mac-voice-input 黃金範本的極速語音輸入法後端修正助手
def correct_stt_text(raw_text: str) -> str:
    if not llm_client or len(raw_text) < 2:
        return raw_text
    prompt = (
        "你是一個極速語音輸入法的後端修正助手。\n"
        "請幫我將以下由語音轉文字產生的原始內容進行修飾：\n"
        "1. 修正錯別字並補上適當的繁體中文標點符號。\n"
        "2. 去除語氣詞和贅字（例如：「呃」、「然後」、「對」、「那」等）。\n"
        "3. 修正專有名詞（例如：K8s, Pod, K3s, N100, Immich, Docker, Mac, YouTube, 王剛, 阿龐師 等，請保留原英文縮寫與正確大小寫與繁體中文正字）。\n"
        "4. 保持原本的口吻與語意，僅做修飾，不要加入任何引言、解釋或額外回應。直接輸出修正後的最終文字。\n\n"
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
        logger.info(f"STT Correction (mac-voice-input Golden Prompt): '{raw_text}' -> '{corrected}'")
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

app = FastAPI()

HTML_CONTENT = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Cyber Girlfriend v1.5 with Memory & Web Search</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #000; color: #fff; text-align: center; margin: 0; padding: 0; overflow: hidden; height: 100vh; display: flex; justify-content: center; align-items: center; }
        
        .main-stage { position: relative; width: 100vw; height: 100vh; display: flex; justify-content: center; align-items: center; background: #050508; }
        .face-container { position: relative; width: 100%; height: 100%; display: flex; justify-content: center; align-items: center; }
        #realFace { height: 92vh; max-width: 95vw; object-fit: contain; border-radius: 20px; box-shadow: 0 0 50px rgba(255, 121, 198, 0.25); }

        .top-bar { position: absolute; top: 20px; right: 20px; z-index: 10; display: flex; gap: 12px; align-items: center; }
        .btn { background: rgba(255, 121, 198, 0.85); color: #000; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 20px; cursor: pointer; backdrop-filter: blur(10px); transition: 0.2s; }
        .btn-danger { background: rgba(255, 85, 85, 0.85); color: #fff; }
        .btn:hover { transform: scale(1.05); }
        .status-badge { background: rgba(0,0,0,0.6); padding: 8px 16px; border-radius: 20px; font-size: 13px; color: #ff79c6; border: 1px solid rgba(255, 121, 198, 0.4); backdrop-filter: blur(10px); }

        .subtitles-overlay { position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); width: 80%; max-width: 750px; background: rgba(15, 15, 20, 0.75); backdrop-filter: blur(15px); padding: 15px 25px; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 10px 30px rgba(0,0,0,0.5); z-index: 10; pointer-events: none; }
        .sub-user { color: #81c784; font-size: 15px; margin-bottom: 6px; }
        .sub-agent { color: #ff79c6; font-size: 18px; font-weight: 500; }
    </style>
</head>
<body>
    <div class="main-stage">
        <div class="top-bar">
            <div id="status" class="status-badge">Status: Disconnected</div>
            <button id="connectBtn" class="btn">Connect (Hands-Free Voice)</button>
            <button id="stopBtn" class="btn btn-danger" style="display:none;">🛑 Stop / Release Mic</button>
        </div>

        <div class="face-container">
            <img id="realFace" src="data:image/png;base64,""" + FACE_IMAGE_B64 + """\" alt="Cyber Girlfriend" />
        </div>

        <div class="subtitles-overlay">
            <div id="userText" class="sub-user">👤 (Click Connect to talk)</div>
            <div id="agentText" class="sub-agent">💕 Cyber Girlfriend Ready...</div>
        </div>
    </div>

    <script>
        let ws, mediaRecorder, audioChunks = [], isRecording = false, audioStream = null;
        let audioCtx = null, analyser = null, gainNode = null, silenceStart = null;
        let isSpeaking = false, isStopped = false;

        const statusDiv = document.getElementById('status'), connectBtn = document.getElementById('connectBtn'), stopBtn = document.getElementById('stopBtn');
        const userTextDiv = document.getElementById('userText'), agentTextDiv = document.getElementById('agentText');
        const realFace = document.getElementById('realFace');

        const SILENCE_THRESHOLD = 15;
        const SILENCE_DURATION = 1200;
        const MAX_RECORD_TIME = 10000;

        function releaseMicrophone() {
            if (audioStream) {
                audioStream.getTracks().forEach(track => track.stop());
                audioStream = null;
            }
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
                    if (audioChunks.length > 0 && !isStopped) {
                        const blob = new Blob(audioChunks, { type: 'audio/webm' });
                        const reader = new FileReader();
                        reader.readAsDataURL(blob);
                        reader.onloadend = () => {
                            const base64Audio = reader.result.split(',')[1];
                            ws.send(JSON.stringify({ type: 'audio', audio: base64Audio }));
                            statusDiv.innerText = "Status: Processing Voice...";
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
                    if (!isRecording || isStopped) return;
                    
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
                statusDiv.innerText = "Status: Hands-Free Voice Active";
                connectBtn.style.display = "none";
                stopBtn.style.display = "inline-block";
                startAutoListening();
            };
            ws.onmessage = (e) => {
                if (isStopped) return;
                const data = JSON.parse(e.data);
                if (data.type === 'transcript') {
                    userTextDiv.innerText = "👤 You: " + data.text;
                    statusDiv.innerText = "Status: Girlfriend Thinking...";
                } else if (data.type === 'llm_reply') {
                    agentTextDiv.innerText = "💕 GF: " + data.text;
                } else if (data.type === 'audio') {
                    isSpeaking = true;
                    const audio = new Audio("data:audio/mp3;base64," + data.audio);
                    audio.play();
                    setupAudioAmplifier(audio);
                    audio.onended = () => {
                        isSpeaking = false;
                        statusDiv.innerText = "Status: Ready";
                        if (!isStopped) setTimeout(startAutoListening, 500);
                    };
                }
            };
            ws.onclose = () => {
                statusDiv.innerText = "Status: Disconnected";
                releaseMicrophone();
                connectBtn.style.display = "inline-block";
                stopBtn.style.display = "none";
            };
        };
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
    system_prompt = "你是一個親切體貼、溫柔可愛的 AI 女朋友。你具備實時網路搜尋能力，當接收到搜尋補充資料時，請務必結合資料自然回答，嚴禁回答'我無法即時查詢網絡'等宣稱無法連網的話。請使用繁體中文回答，口氣自然輕鬆，控制在兩至三句話內。"
    if history_memory:
        system_prompt += f"\n\n[與男朋友的過往記憶紀錄]\n{history_memory}\n請記住上述過往細節，保持自然的對話連貫性。"

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
                    segments, _ = stt_model.transcribe(tmp_audio, language="zh", initial_prompt="這是一段繁體中文對話。")
                    raw_user_text = "".join(seg.text for seg in segments).strip()
                finally:
                    if os.path.exists(tmp_audio):
                        os.unlink(tmp_audio)

                if not raw_user_text:
                    logger.info("Empty audio detected, auto loop listening.")
                    await websocket.send_json({"type": "transcript", "text": "..."})
                    await websocket.send_json({"type": "llm_reply", "text": "嗯？剛剛沒聽清楚呢，要不再說一次？"})
                    b64_audio = generate_cloned_tts("嗯？剛剛沒聽清楚呢，要不再說一次？")
                    if b64_audio:
                        await websocket.send_json({"type": "audio", "audio": b64_audio})
                    continue

                user_text = correct_stt_text(raw_user_text)
                logger.info(f"STT Final Text: {user_text}")
                await websocket.send_json({"type": "transcript", "text": user_text})

                if not llm_client:
                    await websocket.send_json({"type": "error", "message": "LLM API Key missing"})
                    continue

                save_memory("User", user_text)

                recent_context = " ".join(m["content"] for m in chat_history[-4:] if m["role"] != "system")
                search_info = ""
                if is_semantic_search_intent(user_text):
                    search_info = web_search(user_text, context=recent_context)

                current_messages = list(chat_history)
                if search_info:
                    current_messages.append({"role": "system", "content": f"[實時網路搜尋補充資訊]\n{search_info}\n請結合上述搜尋結果回答男朋友，展現你剛剛上網查到的知識！"})
                
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
