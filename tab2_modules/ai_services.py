import os
import sys
import time
import requests
import json
import random
import hashlib
import re # [MỚI] Bùa móc JSON chống AI nói nhảm
from paths import BASE_PATH
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


def _resolve_runtime_file(filename, config):
    candidates = []

    cfg_base = str((config or {}).get("app_base_path", "") or "").strip()
    if cfg_base:
        candidates.append(os.path.join(cfg_base, filename))

    # Ưu tiên thư mục chứa file .exe / thư mục chạy hiện tại
    candidates.append(os.path.join(BASE_PATH, filename))
    candidates.append(os.path.join(os.getcwd(), filename))

    if getattr(sys, 'frozen', False):
        try:
            candidates.append(os.path.join(os.path.dirname(sys.executable), filename))
        except Exception:
            pass

    # Loại trùng vẫn giữ thứ tự ưu tiên
    unique_candidates = []
    for path in candidates:
        if path and path not in unique_candidates:
            unique_candidates.append(path)

    for path in unique_candidates:
        if os.path.exists(path):
            return path, unique_candidates

    return "", unique_candidates

def _normalize_text(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def _format_timeline_text(segments):
    lines = []
    for item in segments:
        text = _normalize_text(item.get("text", ""))
        if not text:
            continue
        start = round(float(item.get("start", 0.0)), 2)
        end = round(float(item.get("end", start)), 2)
        lines.append(f"[{start}s - {end}s]: {text}")
    return "\n".join(lines) + ("\n" if lines else "")


def _parse_timeline_text(raw_voice_text):
    items = []
    pattern = re.compile(r'\[\s*([0-9]+(?:\.[0-9]+)?)s\s*-\s*([0-9]+(?:\.[0-9]+)?)s\s*\]:\s*(.+)')
    for line in (raw_voice_text or "").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        start, end, text = match.groups()
        text = _normalize_text(text)
        if not text:
            continue
        items.append({"start": float(start), "end": float(end), "text": text})
    return items


def _segments_related(text_a, text_b):
    a = _normalize_text(text_a).lower()
    b = _normalize_text(text_b).lower()
    if not a or not b:
        return True

    if a.endswith((",", ":", ";", "-", "–", "...")):
        return True

    connectors = [
        "và", "rồi", "nhưng", "nên", "để", "khi", "vì", "còn",
        "thì", "là", "với", "hay", "hoặc", "sau đó", "đồng thời"
    ]
    if any(b == c or b.startswith(c + " ") for c in connectors):
        return True

    tokens_a = {w for w in re.findall(r'\w+', a, flags=re.UNICODE) if len(w) > 1}
    tokens_b = {w for w in re.findall(r'\w+', b, flags=re.UNICODE) if len(w) > 1}
    if tokens_a & tokens_b:
        return True

    return len(tokens_a) <= 4 or len(tokens_b) <= 4


def _merge_related_short_segments(segments, target_min=4.0, target_max=6.0):
    if not segments:
        return []

    merged = []
    i = 0
    while i < len(segments):
        current = {
            "start": float(segments[i].get("start", 0.0)),
            "end": float(segments[i].get("end", 0.0)),
            "text": _normalize_text(segments[i].get("text", ""))
        }

        while i + 1 < len(segments):
            nxt = {
                "start": float(segments[i + 1].get("start", current["end"])),
                "end": float(segments[i + 1].get("end", current["end"])),
                "text": _normalize_text(segments[i + 1].get("text", ""))
            }
            if not nxt["text"]:
                i += 1
                continue

            current_dur = current["end"] - current["start"]
            combined_dur = nxt["end"] - current["start"]
            gap = max(0.0, nxt["start"] - current["end"])

            if gap > 1.2:
                break

            should_merge = False
            if current_dur < target_min and combined_dur <= target_max + 0.8 and _segments_related(current["text"], nxt["text"]):
                should_merge = True
            elif len(current["text"].split()) <= 6 and combined_dur <= target_max and _segments_related(current["text"], nxt["text"]):
                should_merge = True

            if not should_merge:
                break

            current["end"] = nxt["end"]
            current["text"] = _normalize_text(current["text"].rstrip(", ") + " " + nxt["text"])
            i += 1

            if (current["end"] - current["start"]) >= target_min and current["text"].endswith((".", "!", "?")):
                break

        merged.append(current)
        i += 1

    return merged


def _get_voice_v0_cache_path(config):
    base_path = config.get("app_base_path", os.getcwd())
    cache_dir = os.path.join(base_path, "Workspace_Data")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, "voice_v0_cache.json")


def _load_voice_v0_cache(config):
    cache_path = _get_voice_v0_cache_path(config)
    if not os.path.exists(cache_path):
        return {}

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_voice_v0_cache(config, cache_data):
    cache_path = _get_voice_v0_cache_path(config)
    temp_path = f"{cache_path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, cache_path)


def _fingerprint_voice_text(text):
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _words_to_base_segments(words_list):
    segments = []
    chunk = []

    for word_data in words_list:
        word = _normalize_text(word_data.get('word', ''))
        if word in ['<start>', '<end>', '']:
            continue

        chunk.append({
            "start": float(word_data.get('start_time', 0.0)),
            "end": float(word_data.get('end_time', 0.0)),
            "text": word
        })

        chunk_dur = chunk[-1]["end"] - chunk[0]["start"]
        is_sentence_end = any(word.endswith(p) for p in ['.', '?', '!', ';', ':'])

        if is_sentence_end or chunk_dur >= 5.2 or len(chunk) >= 14:
            segments.append({
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
                "text": " ".join(item["text"] for item in chunk)
            })
            chunk = []

    if chunk:
        segments.append({
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "text": " ".join(item["text"] for item in chunk)
        })

    return segments


def get_drive_service(client_secret_path, base_path):
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    creds = None

    token_dir = base_path if os.path.isdir(base_path) else os.path.dirname(client_secret_path)
    token_path = os.path.join(token_dir, 'token.json')
    
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def get_transcription(voice_path, voice_name, mode, config, log_cb):
    def _transcribe_with_groq():
        log_cb(f"[{voice_name}] Bắt đầu: Gọi Groq bóc băng...")
        url_groq = "https://api.groq.com/openai/v1/audio/transcriptions"
        with open(voice_path, "rb") as f:
            res_groq = requests.post(
                url_groq, 
                headers={"Authorization": f"Bearer {config.get('groq_key')}"}, 
                files={"file": ("v.mp3", f)}, 
                data={"model": "whisper-large-v3", "language": "vi", "response_format": "verbose_json"}, 
                timeout=180
            )
        if res_groq.status_code != 200: raise Exception(f"Lỗi Groq: {res_groq.text}")
        raw_segments = res_groq.json().get("segments", [])
        base_segments = [
            {
                "start": float(s.get("start", 0.0)),
                "end": float(s.get("end", 0.0)),
                "text": _normalize_text(s.get("text", ""))
            }
            for s in raw_segments if _normalize_text(s.get("text", ""))
        ]
        merged_segments = _merge_related_short_segments(base_segments, target_min=4.0, target_max=6.0)
        return _format_timeline_text(merged_segments)

    if mode == "groq":
        return _transcribe_with_groq()

    elif mode == "ohfree":
        # Dò client_secret ở nhiều vị trí, ưu tiên cùng cấp file .exe.
        client_secret, lookup_paths = _resolve_runtime_file("client_secret.json", config)
        base_path = os.path.dirname(client_secret) if client_secret else BASE_PATH

        cookie = config.get("ohfree_cookie", "")
        if not client_secret:
            paths_text = " | ".join(lookup_paths)
            raise Exception(f"Chưa cấu hình client_secret.json! Các đường dẫn đã dò: {paths_text}")
        if not cookie: 
            raise Exception("Chưa cấu hình Cookie OhFree!")

        log_cb(f"[{voice_name}] Đang bơm lên Drive (OhFree Mode)...")
        # Truyền thêm base_path vào để nó lưu token
        drive_service = get_drive_service(client_secret, base_path)
        
        file_metadata = {'name': f"auto_{int(time.time())}.mp3", 'parents': ["1K3iG8kCf8BEGYps9Q1pXWShuukGsEgas"]} # Sửa ID thư mục Drive của bác nếu cần
        media = MediaFileUpload(voice_path, mimetype='audio/mpeg')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        
        try:
            drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
            drive_link = f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link"
            log_cb(f"[{voice_name}] Đang bắn link cho OhFree bóc băng...")
            res = requests.post("https://tts.ohfree.me/api/mp3-to-text", headers={"User-Agent": "Mozilla/5.0", "Cookie": cookie}, files={'url': (None, drive_link)}, timeout=300)
            if res.status_code != 200: raise Exception(f"OhFree từ chối: {res.text[:100]}")
            
            words_list = res.json().get('data', {}).get('words', [])
            if not words_list: raise Exception("OhFree không trả về text!")
            base_segments = _words_to_base_segments(words_list)
            merged_segments = _merge_related_short_segments(base_segments, target_min=4.0, target_max=6.0)
            return _format_timeline_text(merged_segments)
        finally:
            try: drive_service.files().delete(fileId=file_id).execute()
            except: pass

    # Nếu mode lạ thì fallback về Groq
    return _transcribe_with_groq()

# =====================================================
# AI API HELPER FUNCTIONS FOR DIRECTOR
# =====================================================
def _call_ai_director(prompt, config, provider="kie", model="gpt-4o", temperature=0.5, timeout=180, log_cb=None):
    """
    Universal AI API caller cho director functions
    
    Args:
        prompt: Prompt text
        config: Config dict chứa API keys  
        provider: "kie", "openai" hoặc "shopaikey"
        model: Model name
        temperature: Temperature setting
        timeout: Request timeout
        
    Returns:
        Response text từ AI
    """
    import time
    import requests
    
    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        api_key = config.get("openai_key", "")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature
        }
    elif provider == "shopaikey":
        url = f"https://api.shopaikey.com/v1beta/models/{model}"
        api_key = config.get("shopaikey_key", "")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature
            }
        }
    else:  # kie.ai
        url = "https://api.kie.ai/gemini-3-flash/v1/chat/completions"
        api_key = config.get("kie_key", "")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }
    
    time.sleep(2)  # Rate limiting
    res = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if res.status_code != 200:
        raise Exception(f"Lỗi {provider.upper()} API: {res.status_code} - {res.text}")
    
    if provider == "shopaikey":
        data = res.json()
        candidates = data.get("candidates", [])
        parts = (candidates[0].get("content", {}).get("parts", []) if candidates else [])
        text = parts[0].get("text", "") if parts else ""

        try:
            url_usage = "https://api.shopaikey.com/usage/histories"
            headers_usage = {"x-api-key": api_key}
            payload_usage = {"page": 1, "page_size": 1}
            usage_res = requests.post(url_usage, headers=headers_usage, json=payload_usage, timeout=30)
            if usage_res.status_code == 200:
                usage_data = usage_res.json() or {}
                items = (((usage_data.get("data") or {}).get("items")) or [])
                if items:
                    item = items[0]
                    prompt_tokens = item.get("prompt_tokens", 0)
                    completion_tokens = item.get("completion_tokens", 0)
                    cost = item.get("cost", 0)
                    model_name = item.get("model_name", "")
                    msg = (
                        f"ShopAIKey usage - prompt: {prompt_tokens}, "
                        f"completion: {completion_tokens}, cost: ${cost}"
                    )
                    if model_name:
                        msg += f", model: {model_name}"
                    if log_cb:
                        log_cb(msg, provider="shopaikey")
                    else:
                        print(msg)
        except Exception:
            pass

        return text

    return res.json()["choices"][0]["message"]["content"]


def _extract_json_from_response(text):
    """Trích xuất JSON array từ response text và sửa lỗi trailing commas"""
    import re
    import json
    
    json_str = ""
    match = re.search(r'```json\s*(\[.*?\])\s*```', text, re.DOTALL | re.IGNORECASE)
    if match:
        json_str = match.group(1)
    else:
        match = re.search(r'```\s*(\[.*?\])\s*```', text, re.DOTALL)
        if match:
            json_str = match.group(1)
        else:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                json_str = match.group(0)
            else:
                raise ValueError("Không thể tìm thấy mảng JSON hợp lệ!")
    
    # Xóa dấu phẩy thừa ở cuối mảng/object
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    return json.loads(json_str)

def get_director_timeline(voice_text, broll_text, config, log_cb, voice_name, project_context="", provider=None, model=None, opening_state=None, broll_usage=None, global_broll_state=None):
    import time
    import requests
    import json
    import re
    
    # Lấy provider và model từ config nếu không được truyền vào
    if provider is None:
        provider = config.get("ai_provider", "kie")
    if model is None:
        if provider == "shopaikey":
            model = config.get("gemini_model", "gemini-2.5-flash:generateContent")
        elif provider == "kie":
            model = config.get("kie_model", "gemini-3-flash")
        else:
            model = config.get("openai_model", "gpt-4o")
    
    # Gọi AI Vòng 0 để "Gom câu chống giật" trước khi Đạo diễn Vòng 1 làm việc (có thể tắt).
    if config.get("enable_v0", True):
        voice_text = optimize_voice_timeline_by_ai(voice_text, config, log_cb, voice_name, provider, model)
    else:
        log_cb(f"[{voice_name}] ⏭️ VÒNG 0 tắt, dùng SRT gốc.")
    
    # Sử dụng helper function để extract JSON
    extract_json_array = _extract_json_from_response

    # =========================================================
    # VÒNG 1/2: CHIA CỤM (WINDOWING) + CHẤM ĐIỂM SEMANTIC NHẸ
    # =========================================================
    context_line = f"BỐI CẢNH SẢN PHẨM ĐANG QUẢNG CÁO: {project_context}" if project_context and project_context != "Không có mô tả cụ thể." else ""
    log_cb(f"[{voice_name}] Đạo diễn AI: Dùng windowing (5-8 câu, overlap 1 câu) để tăng chất lượng.")
    if context_line:
        log_cb(f"[{voice_name}] 🎯 Context: {project_context[:60]}..." if len(project_context) > 60 else f"[{voice_name}] 🎯 Context: {project_context}")

    blocked_openings = []
    if opening_state and isinstance(opening_state, dict):
        blocked_openings = list(opening_state.get("used", []) or [])
    blocked_text = "\nDANH SACH CAM (canh mo dau da dung trong batch): " + ", ".join(blocked_openings) if blocked_openings else ""

    def _chunk_timeline_items(items, min_size=5, max_size=8, overlap=1):
        chunks = []
        i = 0
        total = len(items)
        while i < total:
            end = min(i + max_size, total)
            if end - i < min_size and chunks:
                chunks[-1].extend(items[i:end])
                break
            chunk = items[i:end]
            chunks.append(chunk)
            next_i = end - overlap
            if next_i <= i:
                next_i = end
            i = next_i
        return chunks

    def _filter_broll_text(broll_full, candidates_set):
        if not broll_full or not candidates_set:
            return broll_full
        lines = [line for line in broll_full.splitlines() if any(c in line for c in candidates_set)]
        return "\n".join(lines) if lines else broll_full

    def _score_candidates(raw_chunk, chunk_broll_text):
        if not raw_chunk:
            return raw_chunk
        candidates_json_str = json.dumps(raw_chunk, ensure_ascii=False, indent=2)
        prompt_score = f"""Bạn là trợ lý chấm điểm semantic.
{context_line}

Dưới đây là danh sách câu thoại + candidates cần chấm điểm:
{candidates_json_str}

Thông tin kho video (mô tả):
{chunk_broll_text}

YÊU CẦU:
1. Chấm điểm relevance từng candidate theo thang 1-5.
2. Sắp xếp candidates theo điểm giảm dần.
3. Trả về JSON array, giữ nguyên start/end/text.
4. Thêm key "scores" (mảng điểm) cùng thứ tự với candidates.
"""
        try:
            raw_score = _call_ai_director(prompt_score, config, provider, model, temperature=0.1, log_cb=log_cb)
            scored = extract_json_array(raw_score)
            if not isinstance(scored, list):
                return raw_chunk
            return scored
        except Exception:
            return raw_chunk

    parsed_voice = _parse_timeline_text(voice_text)
    if parsed_voice:
        voice_chunks = _chunk_timeline_items(parsed_voice, min_size=5, max_size=8, overlap=1)
    else:
        voice_chunks = [None]

    raw_timeline = []
    final_timeline = []
    seen_raw_keys = set()
    seen_final_keys = set()

    for idx, chunk_items in enumerate(voice_chunks, start=1):
        if chunk_items:
            chunk_voice_text = _format_timeline_text(chunk_items)
        else:
            chunk_voice_text = voice_text

        log_cb(f"[{voice_name}] Vòng 1 (cụm {idx}/{len(voice_chunks)}): Đang lọc rổ video...")

        prompt_1 = f"""BẠN LÀ ĐẠO DIỄN PHIM CHUYÊN NGHIỆP.
{context_line}
    {blocked_text}

Dưới đây là Kho video có kèm theo MÔ TẢ CHI TIẾT và [SỐ LẦN ĐÃ DÙNG] của từng cảnh:
{broll_text}

Nội dung Voice (Giọng đọc):
{chunk_voice_text}

VÒNG 1 - TÌM KIẾM ỨNG VIÊN (THẮT CHẶT):
1. Đọc kỹ từng câu thoại.
2. Chọn ra TỪ 3 ĐẾN 5 VIDEO ỨNG VIÊN phù hợp nhất về mặt ngữ nghĩa VÀ BỐI CẢNH SẢN PHẨM cho câu thoại đó.
3. Ưu tiên nhặt những video có "Đã dùng: 0 lần" hoặc số lần dùng thấp.
4. Với câu mở đầu, TRÁNH các video nằm trong danh sách cấm nếu còn ứng viên khác.
5. BẮT BUỘC trả về ĐÚNG CÚ PHÁP JSON (có dấu ngoặc kép ở các key):
[ {{"start": 0.0, "end": 2.5, "text": "...", "candidates": ["vid1.mp4", "vid2.mp4"]}} ]"""

        raw_chunk = []
        for attempt in range(3):
            try:
                raw_text_1 = _call_ai_director(prompt_1, config, provider, model, temperature=0.5, log_cb=log_cb)
                raw_chunk = extract_json_array(raw_text_1)
                break
            except Exception as e:
                if attempt == 2:
                    raise Exception(f"Lỗi Vòng 1 (Cụm {idx}) sau 3 lần: {str(e)}")
                log_cb(f"[{voice_name}] ⚠️ Vòng 1 cụm {idx} lỗi JSON, thử lại (Lần {attempt+2}/3)...")

        candidates_set = set()
        for item in raw_chunk:
            candidates_set.update(item.get("candidates", []) if isinstance(item.get("candidates", []), list) else [])
        chunk_broll_text = _filter_broll_text(broll_text, candidates_set)
        scored_chunk = _score_candidates(raw_chunk, chunk_broll_text)

        log_cb(f"[{voice_name}] Vòng 2 (cụm {idx}/{len(voice_chunks)}): Ghép chuỗi cảnh...")
        candidates_json_str = json.dumps(scored_chunk, ensure_ascii=False, indent=2)

        prompt_2 = f"""BẠN LÀ ĐẠO DIỄN PHIM CHUYÊN NGHIỆP.
{context_line}
    {blocked_text}

Dưới đây là Kịch bản nháp (gồm start/end của câu thoại) và danh sách Video Ứng Viên:
{candidates_json_str}

Thông tin chi tiết (Độ dài giây, Mô tả, Số lần dùng) của toàn bộ kho:
{chunk_broll_text}

VÒNG 2 - CHỐT HẠ CHUỖI VIDEO (THẮT CHẶT):
1. Tính Thời lượng câu thoại (end - start).
2. Chọn video từ mảng 'candidates' ưu tiên Số lần dùng thấp nhất.
3. Với câu mở đầu, tránh video trong danh sách cấm nếu còn lựa chọn khác.
4. CHIẾN LƯỢC NỐI CẢNH: 
   - Nếu video ngắn hơn thời lượng thoại -> CHỌN THÊM video từ rổ ứng viên ghép vào.
   - Tổng độ dài các video được chọn phải lớn hơn hoặc bằng thời lượng thoại.
   - TUYỆT ĐỐI KHÔNG chọn lặp lại 1 video 2 lần trong cùng 1 câu thoại.
4. BẮT BUỘC trả về ĐÚNG CÚ PHÁP JSON (có dấu ngoặc kép ở các key):
[ {{"start": 0.0, "end": 4.5, "text": "...", "video_files": ["vid_1.mp4", "vid_2.mp4"]}} ]"""

        final_chunk = []
        for attempt in range(3):
            try:
                raw_text_2 = _call_ai_director(prompt_2, config, provider, model, temperature=0.2, log_cb=log_cb)
                final_chunk = extract_json_array(raw_text_2)
                break
            except Exception as e:
                if attempt == 2:
                    raise Exception(f"Lỗi Vòng 2 (Cụm {idx}) sau 3 lần: {str(e)}")
                log_cb(f"[{voice_name}] ⚠️ Vòng 2 cụm {idx} lỗi JSON, thử lại (Lần {attempt+2}/3)...")

        for item in scored_chunk:
            key = (item.get("start"), item.get("end"), item.get("text"))
            if key in seen_raw_keys:
                continue
            seen_raw_keys.add(key)
            raw_timeline.append(item)

        for item in final_chunk:
            key = (item.get("start"), item.get("end"), item.get("text"))
            if key in seen_final_keys:
                continue
            seen_final_keys.add(key)
            final_timeline.append(item)

    # =========================================================
    # KIỂM TRA BẢO HIỂM LẦN CUỐI (SAFETY NET)
    # =========================================================
    for item in final_timeline:
        if "video_files" not in item or not isinstance(item["video_files"], list) or len(item["video_files"]) == 0:
            item["video_files"] = []
            for raw_item in raw_timeline:
                if raw_item.get("text") == item.get("text") and raw_item.get("candidates"):
                    item["video_files"] = [raw_item["candidates"][0]]
                    break
            if not item.get("video_files"):
                item["video_files"] = []

    # =========================================================
    # [MỚI] KIỂM TRA & NGĂN VIDEO LẶP GIỮA CÁC CÂU THOẠI
    # =========================================================
    def prevent_duplicate_videos(timeline, candidates_map):
        """Quét timeline và thay thế video lặp bằng ứng viên khác"""
        global_used = set()
        
        for idx, row in enumerate(timeline):
            row_text = row.get("text", "")
            candidates = candidates_map.get(row_text, [])
            current_vids = row.get("video_files", [])
            new_vids = []
            
            for vid in current_vids:
                if vid not in global_used:
                    # Video này chưa dùng, nhận cho câu này
                    new_vids.append(vid)
                    global_used.add(vid)
                else:
                    # Video này đã dùng, tìm video thay thế từ ứng viên
                    replaced = False
                    for candidate in candidates:
                        if candidate not in global_used and candidate not in new_vids:
                            new_vids.append(candidate)
                            global_used.add(candidate)
                            replaced = True
                            log_cb(f"[{voice_name}] ⚠️ Video '{vid}' bị lặp, đã thay bằng '{candidate}'.")
                            break
                    
                    if not replaced:
                        # Không tìm được ứng viên mới, cảnh báo nhưng vẫn giữ lại
                        log_cb(f"[{voice_name}] ⚠️ Video '{vid}' bị lặp, không tìm được thay thế, tạm giữ lại.")
                        new_vids.append(vid)
            
            row["video_files"] = new_vids if new_vids else current_vids
        
        return timeline
    
    # Build candidates map từ raw_timeline
    candidates_map = {item.get("text", ""): item.get("candidates", []) for item in raw_timeline}
    final_timeline = prevent_duplicate_videos(final_timeline, candidates_map)
    log_cb(f"[{voice_name}] ✅ Kiểm tra xong - Video trong video không bị lặp.")

    def usage_score(vid):
        if isinstance(broll_usage, dict):
            return int(broll_usage.get(vid, 999999))
        return 999999

    # =========================================================
    # [MỚI] ÉP KHÁC NHAU TẤT CẢ CẢNH GIỮA CÁC VIDEO TRONG BATCH
    # =========================================================
    if final_timeline and global_broll_state and isinstance(global_broll_state, dict):
        used_set = global_broll_state.get("used")
        lock = global_broll_state.get("lock")
        if isinstance(used_set, set):
            for row in final_timeline:
                row_text = row.get("text", "")
                candidates = candidates_map.get(row_text, [])
                current_vids = row.get("video_files", [])
                if not current_vids:
                    continue

                new_vids = []
                for vid in current_vids:
                    with lock:
                        already_used = vid in used_set

                    if not already_used:
                        with lock:
                            used_set.add(vid)
                        new_vids.append(vid)
                        continue

                    pool = [c for c in candidates if c not in new_vids]
                    with lock:
                        unused_pool = [c for c in pool if c not in used_set]

                    choice_pool = unused_pool if unused_pool else pool
                    if choice_pool:
                        selected = sorted(
                            choice_pool,
                            key=lambda v: (usage_score(v), candidates.index(v) if v in candidates else 999999)
                        )[0]
                        with lock:
                            used_set.add(selected)
                        if selected != vid:
                            log_cb(f"[{voice_name}] ⚠️ Cảnh '{vid}' trùng batch, đổi sang '{selected}'.")
                        else:
                            log_cb(f"[{voice_name}] ⚠️ Cảnh '{vid}' trùng batch, không có cảnh mới để đổi.")
                        new_vids.append(selected)
                    else:
                        log_cb(f"[{voice_name}] ⚠️ Cảnh '{vid}' trùng batch, không có ứng viên thay thế.")
                        new_vids.append(vid)

                row["video_files"] = new_vids if new_vids else current_vids

    # =========================================================
    # [MỚI] ÉP KHÁC NHAU CẢNH MỞ ĐẦU GIỮA CÁC VIDEO TRONG BATCH
    # =========================================================
    if final_timeline and opening_state and isinstance(opening_state, dict):
        used_set = opening_state.get("used")
        lock = opening_state.get("lock")
        global_used = None
        global_lock = None
        if global_broll_state and isinstance(global_broll_state, dict):
            global_used = global_broll_state.get("used")
            global_lock = global_broll_state.get("lock")
        if isinstance(used_set, set):
            first_row = min(final_timeline, key=lambda item: float(item.get("start", 0.0)))
            row_text = first_row.get("text", "")
            candidates = candidates_map.get(row_text, [])
            current = first_row.get("video_files", [])
            if not candidates:
                candidates = current

            preferred = [v for v in candidates if v not in used_set]
            if isinstance(global_used, set):
                preferred = [v for v in preferred if v not in global_used]
            pool = preferred if preferred else candidates
            if pool:
                selected = sorted(pool, key=lambda v: (usage_score(v), candidates.index(v) if v in candidates else 999999))[0]
                if lock:
                    with lock:
                        if selected not in used_set:
                            used_set.add(selected)
                else:
                    used_set.add(selected)

                if isinstance(global_used, set):
                    if global_lock:
                        with global_lock:
                            if selected not in global_used:
                                global_used.add(selected)
                    else:
                        global_used.add(selected)

                if not current:
                    first_row["video_files"] = [selected]
                else:
                    first_row["video_files"] = [selected] + [v for v in current if v != selected]

                if preferred:
                    log_cb(f"[{voice_name}] ✅ Cảnh mở đầu ưu tiên khác nhau: {selected}")
                else:
                    log_cb(f"[{voice_name}] ⚠️ Hết lựa chọn mới, phải dùng lại cảnh mở đầu: {selected}")

    return final_timeline


def optimize_voice_timeline_by_ai(raw_voice_text, config, log_cb, voice_name, provider=None, model=None):
    import time
    import requests
    import json
    import re
    
    # Lấy provider và model từ config nếu không được truyền vào
    if provider is None:
        provider = config.get("ai_provider", "kie")
    if model is None:
        if provider == "shopaikey":
            model = config.get("gemini_model", "gemini-2.5-flash:generateContent")
        elif provider == "kie":
            model = config.get("kie_model", "gemini-3-flash")
        else:
            model = config.get("openai_model", "gpt-4o")
    
    # Hàm bóc vỏ JSON (Tái sử dụng lại cho chắc cú)
    extract_json_array = _extract_json_from_response

    def merge_micro_segments_only(segments, short_max=3.0):
        if not segments:
            return []

        merged = []
        i = 0
        while i < len(segments):
            current = {
                "start": float(segments[i].get("start", 0.0)),
                "end": float(segments[i].get("end", 0.0)),
                "text": _normalize_text(segments[i].get("text", "")),
            }

            while i + 1 < len(segments):
                nxt = {
                    "start": float(segments[i + 1].get("start", current["end"])),
                    "end": float(segments[i + 1].get("end", current["end"])),
                    "text": _normalize_text(segments[i + 1].get("text", "")),
                }
                if not nxt["text"]:
                    i += 1
                    continue

                current_dur = current["end"] - current["start"]
                next_dur = nxt["end"] - nxt["start"]
                combined_dur = nxt["end"] - current["start"]
                gap = max(0.0, nxt["start"] - current["end"])

                if gap > 1.0:
                    break

                short_pair = current_dur <= short_max or next_dur <= short_max
                should_merge = short_pair and _segments_related(current["text"], nxt["text"]) and combined_dur <= max(6.0, short_max * 2)

                if not should_merge:
                    break

                current["end"] = nxt["end"]
                current["text"] = _normalize_text(current["text"].rstrip(", ") + " " + nxt["text"])
                i += 1

            merged.append(current)
            i += 1

        return merged

    def has_short_segments(segments, short_max=3.0):
        return any((float(item.get("end", 0.0)) - float(item.get("start", 0.0))) <= short_max for item in segments)

    def build_tail_prompt(tail_voice_text, hook_context=""):
        context_block = ""
        if hook_context:
            context_block = f"\n\nBỐI CẢNH TRƯỚC ĐÓ (KHÔNG SỬA, CHỈ THAM KHẢO MẠCH):\n{hook_context}"
        return f"""Đây là phần kịch bản giọng đọc SAU hook đầu đã cố định.{context_block}

YÊU CẦU:
1. Chỉ làm mượt các đoạn bị ngắn quá, ưu tiên những đoạn khoảng 2-3 giây.
2. Không cố nối các đoạn dài; nếu hai đoạn khác ý rõ ràng thì giữ riêng.
3. Không được tạo thêm nội dung mới. Không đổi ý, không thêm ý.
4. Giữ đúng THỨ TỰ nội dung. Nếu gộp thì start = đoạn đầu, end = đoạn cuối.
5. Chỉ trả về JSON array đúng cú pháp, dạng:
[ {{\"start\": 0.0, \"end\": 3.2, \"text\": \"...\"}} ]

NỘI DUNG CẦN XỬ LÝ:
{tail_voice_text}"""

    parsed_items = _parse_timeline_text(raw_voice_text)
    if parsed_items:
        cache_key = _fingerprint_voice_text(raw_voice_text)
        cache_data = _load_voice_v0_cache(config)

        hook_item = parsed_items[:1]
        hook_text = _format_timeline_text(hook_item)
        tail_items = parsed_items[1:]

        # Hook đầu giữ nguyên, chỉ nắn lại các đoạn sau nếu chúng thực sự ngắn.
        tail_items = merge_micro_segments_only(tail_items, short_max=3.0)
        tail_text = _format_timeline_text(tail_items)
        raw_voice_text = tail_text
    else:
        cache_data = {}
        hook_text = ""
        tail_text = raw_voice_text

    log_cb(f"[{voice_name}] VÒNG 0: Đang làm mượt phần sau hook đầu, chỉ ưu tiên đoạn ngắn 2-3s...")
    
    prompt_0 = build_tail_prompt(raw_voice_text, hook_text)

    optimized_text = ""
    for attempt in range(3):
        try:
            raw_out = _call_ai_director(prompt_0, config, provider, model, temperature=0.2, log_cb=log_cb)
            final_json = extract_json_array(raw_out)
            final_json = merge_micro_segments_only(final_json, short_max=3.0)
            optimized_text = _format_timeline_text(final_json)
            break
        except Exception as e:
            if attempt == 2:
                log_cb(f"[{voice_name}] ⚠️ Vòng 0 thất bại. Bỏ qua và dùng kịch bản gốc.")
                return f"{hook_text}{tail_text}" # Lỗi thì trả về kịch bản gốc, không làm gián đoạn
            log_cb(f"[{voice_name}] ⚠️ Vòng 0 AI gom câu bị vấp, đang thử lại (Lần {attempt+2}/3)...")

    final_text = optimized_text if optimized_text else tail_text
    if parsed_items:
        final_text = f"{hook_text}{_format_timeline_text(_parse_timeline_text(final_text))}" if final_text else f"{hook_text}{tail_text}"
        cache_data[cache_key] = final_text
        _save_voice_v0_cache(config, cache_data)

    return final_text if final_text else raw_voice_text