import os
import time
import requests
import json
import random
import re # [MỚI] Bùa móc JSON chống AI nói nhảm
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def get_drive_service(client_secret_path, base_path):
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    creds = None
    
    token_path = os.path.join(base_path, 'token.json')
    
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
    if mode == "groq":
        log_cb(f"[{voice_name}] Bắt đầu: Gọi Groq bóc băng...")
        url_groq = "[https://api.groq.com/openai/v1/audio/transcriptions](https://api.groq.com/openai/v1/audio/transcriptions)"
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
        return "".join([f"[{round(s['start'], 2)}s - {round(s['end'], 2)}s]: {s['text'].strip()}\n" for s in raw_segments])

    elif mode == "ohfree":
        # =================================================================
        # [ĐÃ SỬA] DÙNG LA BÀN TÌM ĐÚNG FILE CLIENT_SECRET CẠNH CỤC EXE
        # =================================================================
        base_path = config.get("app_base_path", os.getcwd())
        client_secret = os.path.join(base_path, "client_secret.json")
        
        cookie = config.get("ohfree_cookie", "")
        if not os.path.exists(client_secret): 
            raise Exception(f"Chưa cấu hình client_secret.json! Hãy để file này cạnh file .exe nhé. (Đang tìm tại: {client_secret})")
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
            return "".join([f"[{w['start_time']}s - {w['end_time']}s]: {w['word']}\n" for w in words_list if w['word'] not in ['<start>', '<end>', '']])
        finally:
            try: drive_service.files().delete(fileId=file_id).execute()
            except: pass

def get_director_timeline(voice_text, broll_text, config, log_cb, voice_name):
    import time
    import requests
    import json
    import re
    
    # =========================================================
    # Hàm Bóc Vỏ JSON & Sửa Lỗi Vặt (Trailing Commas)
    # =========================================================
    def extract_json_array(text):
        json_str = ""
        match = re.search(r'```json\s*(\[.*?\])\s*```', text, re.DOTALL | re.IGNORECASE)
        if match: json_str = match.group(1)
        else:
            match = re.search(r'```\s*(\[.*?\])\s*```', text, re.DOTALL)
            if match: json_str = match.group(1)
            else:
                match = re.search(r'\[.*\]', text, re.DOTALL)
                if match: json_str = match.group(0)
                else: raise ValueError("Không thể tìm thấy mảng JSON hợp lệ!")
                
        # [BÙA MỚI] Xóa dấu phẩy thừa ở cuối mảng/object (Lỗi AI hay mắc nhất)
        json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
        return json.loads(json_str)

    url_kie = "https://api.kie.ai/gemini-2.5-flash/v1/chat/completions"
    headers = {"Authorization": f"Bearer {config.get('kie_key')}", "Content-Type": "application/json"}

    # =========================================================
    # VÒNG 1: TRỢ LÝ AI (CÓ CƠ CHẾ THỬ LẠI 3 LẦN)
    # =========================================================
    log_cb(f"[{voice_name}] Đạo diễn AI Vòng 1: Đang lọc rổ video ứng viên...")
    
    prompt_1 = f"""Dưới đây là Kho video có kèm theo MÔ TẢ CHI TIẾT và [SỐ LẦN ĐÃ DÙNG] của từng cảnh:
{broll_text}

Nội dung Voice (Giọng đọc):
{voice_text}

VÒNG 1 - TÌM KIẾM ỨNG VIÊN:
1. Đọc kỹ từng câu thoại.
2. Chọn ra TỪ 3 ĐẾN 5 VIDEO ỨNG VIÊN phù hợp nhất về mặt ngữ nghĩa cho câu thoại đó.
3. Ưu tiên nhặt những video có "Đã dùng: 0 lần" hoặc số lần dùng thấp.
4. BẮT BUỘC trả về ĐÚNG CÚ PHÁP JSON (có dấu ngoặc kép ở các key):
[ {{"start": 0.0, "end": 2.5, "text": "...", "candidates": ["vid1.mp4", "vid2.mp4"]}} ]"""
            
    payload_1 = {"model": "gemini-2.5-flash", "messages": [{"role": "user", "content": prompt_1}], "temperature": 0.5}
    
    raw_timeline = []
    for attempt in range(3): # Vòng lặp tái sinh
        try:
            time.sleep(2)
            res_1 = requests.post(url_kie, headers=headers, json=payload_1, timeout=180)
            if res_1.status_code != 200: raise Exception(f"Lỗi API Vòng 1: {res_1.text}")
            
            raw_text_1 = res_1.json()["choices"][0]["message"]["content"]
            raw_timeline = extract_json_array(raw_text_1)
            break # Nếu thành công thì thoát vòng lặp ngay
        except Exception as e:
            if attempt == 2: raise Exception(f"Lỗi Vòng 1 (Đã thử 3 lần vẫn hỏng JSON): {str(e)}")
            log_cb(f"[{voice_name}] ⚠️ Vòng 1 AI viết sai chính tả JSON, đang ép AI viết lại (Lần {attempt+2}/3)...")

    # =========================================================
    # VÒNG 2: TỔNG ĐẠO DIỄN AI (CÓ CƠ CHẾ THỬ LẠI 3 LẦN)
    # =========================================================
    log_cb(f"[{voice_name}] Đạo diễn AI Vòng 2: Đo đạc thời lượng & Ghép chuỗi cảnh...")
    
    candidates_json_str = json.dumps(raw_timeline, ensure_ascii=False, indent=2)
    
    prompt_2 = f"""Dưới đây là Kịch bản nháp (gồm start/end của câu thoại) và danh sách Video Ứng Viên:
{candidates_json_str}

Thông tin chi tiết (Độ dài giây, Mô tả, Số lần dùng) của toàn bộ kho:
{broll_text}

VÒNG 2 - CHỐT HẠ CHUỖI VIDEO:
1. Tính Thời lượng câu thoại (end - start).
2. Chọn video từ mảng 'candidates' ưu tiên Số lần dùng thấp nhất.
3. CHIẾN LƯỢC NỐI CẢNH: 
   - Nếu video ngắn hơn thời lượng thoại -> CHỌN THÊM video từ rổ ứng viên ghép vào.
   - Tổng độ dài các video được chọn phải lớn hơn hoặc bằng thời lượng thoại.
   - TUYỆT ĐỐI KHÔNG chọn lặp lại 1 video 2 lần trong cùng 1 câu thoại.
4. BẮT BUỘC trả về ĐÚNG CÚ PHÁP JSON (có dấu ngoặc kép ở các key):
[ {{"start": 0.0, "end": 4.5, "text": "...", "video_files": ["vid_1.mp4", "vid_2.mp4"]}} ]"""

    payload_2 = {"model": "gemini-2.5-flash", "messages": [{"role": "user", "content": prompt_2}], "temperature": 0.2}
    
    final_timeline = []
    for attempt in range(3): # Vòng lặp tái sinh
        try:
            time.sleep(2)
            res_2 = requests.post(url_kie, headers=headers, json=payload_2, timeout=180)
            if res_2.status_code != 200: raise Exception(f"Lỗi API Vòng 2: {res_2.text}")
            
            raw_text_2 = res_2.json()["choices"][0]["message"]["content"]
            final_timeline = extract_json_array(raw_text_2)
            break # Thành công thì thoát
        except Exception as e:
            if attempt == 2: raise Exception(f"Lỗi Vòng 2 (Đã thử 3 lần vẫn hỏng JSON): {str(e)}")
            log_cb(f"[{voice_name}] ⚠️ Vòng 2 AI viết sai chính tả JSON, đang ép AI viết lại (Lần {attempt+2}/3)...")

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

    return final_timeline