import os, re, time, requests, random
from datetime import datetime
from moviepy.editor import VideoFileClip
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

class YTDLpLogger(object):
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

class ScraperHandler:
    def __init__(self, ui_tab):
        self.ui = ui_tab
        self.folder_id = "1K3iG8kCf8BEGYps9Q1pXWShuukGsEgas" # ID thư mục Drive của sếp

    def json_to_flat_text(self, words_list, output_path):
        text_content = " ".join([w.get('word', '').strip() for w in words_list if w.get('word', '').strip() not in ['<start>', '<end>', '']])
        with open(output_path, "w", encoding="utf-8") as f: f.write(text_content)

    def clean_filename(self, title):
        return re.sub(r'[\\/*?:"<>|]', "", title)[:50].strip()

    def download_single(self, url, index, save_dir):
        is_success = False
        if self.ui.use_ytdlp.get():
            try:
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]', 
                    'merge_output_format': 'mp4',
                    'outtmpl': os.path.join(save_dir, '%(title).50s_[%(id)s].%(ext)s'),
                    'quiet': True, 'no_warnings': True, 'ignoreerrors': True, 'nocheckcertificate': True,
                    'logger': YTDLpLogger() 
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if info is None or (info.get('vcodec') == 'none' and not info.get('requested_formats')):
                        raise Exception("Lỗi cấu trúc Video")
                    ydl.download([url])
                    return ydl.prepare_filename(info)
            except Exception:
                self.ui.add_log(f"⚠️ [Bẻ Lái] yt-dlp nghẽn, đẩy link sang TikWM: {url[:20]}...")
                is_success = False

        if not is_success:
            time.sleep(index * 1.5)
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    res = requests.post("https://www.tikwm.com/api/", data={"url": url, "count": 12, "cursor": 0, "web": 1, "hd": 1}, timeout=20) 
                    if res.status_code != 200: raise Exception("Server TikWM ngâm kết nối.")
                    data = res.json()
                    if data.get("code") != 0: raise Exception(data.get("msg", "Link sai/Riêng tư."))
                    
                    play_url = data.get("data", {}).get("play")
                    if not play_url: raise Exception("Không tìm thấy link MP4.")
                    if play_url.startswith("/"): play_url = "https://www.tikwm.com" + play_url

                    safe_title = self.clean_filename(data.get("data", {}).get("title", "TikTok_Video")) or f"Vid_{datetime.now().strftime('%H%M%S_%f')}" 
                    file_name = f"{safe_title}.mp4"
                    save_path = os.path.join(save_dir, file_name)

                    counter = 1
                    while os.path.exists(save_path):
                        save_path = os.path.join(save_dir, f"{os.path.splitext(file_name)[0]}_{counter}.mp4")
                        counter += 1

                    vid_res = requests.get(play_url, stream=True, timeout=30)
                    if vid_res.status_code == 200:
                        with open(save_path, 'wb') as f:
                            for chunk in vid_res.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        return save_path
                    else: raise Exception(f"Lỗi kéo MP4 (HTTP {vid_res.status_code})")
                except Exception as e:
                    if "1 request/second" in str(e) and attempt < max_retries - 1:
                        time.sleep(3)
                        continue 
                    return None 
            return None

    def process_single_url(self, url, index, target_dir, cookie):
        time.sleep(random.uniform(1.0, 3.0))
        self.ui.add_log(f"⏳ [Luồng {index+1}] Xử lý: {url[:30]}...")
        
        temp_video = temp_audio = file_id = drive_service = None

        try:
           # 1. TẢI VIDEO & TÁCH MP3
            temp_video = self.download_single(url, index, target_dir)
            if not temp_video or not os.path.exists(temp_video): raise Exception("Kéo video thất bại.")
            
            base_name = os.path.splitext(os.path.basename(temp_video))[0]
            temp_audio = os.path.join(target_dir, f"{base_name}_{index}.mp3")
            txt_output = os.path.join(target_dir, f"KB_{base_name[:15]}_{int(time.time())}.txt")

            video = VideoFileClip(temp_video)
            video.audio.write_audiofile(temp_audio, logger=None)
            video.close()

            # =======================================================
            # [ĐÃ SỬA LẠI] ĐỌC TRỰC TIẾP TỪ NÚT BẤM TRÊN GIAO DIỆN TAB 7
            # =======================================================
            mode = self.ui.boc_bang_mode.get()

            # 2. RẼ NHÁNH BÓC BĂNG
            if mode == "groq":
                self.ui.add_log(f"[{index+1}] Đang bóc băng siêu tốc bằng Groq...")
                groq_key = self.ui.main_app.config.get("groq_key", "")
                if not groq_key: raise Exception("Chưa cấu hình Groq Key ở Tab 2!")
                
                with open(temp_audio, "rb") as f:
                    res = requests.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions", 
                        headers={"Authorization": f"Bearer {groq_key}"}, 
                        files={"file": ("v.mp3", f)}, 
                        data={"model": "whisper-large-v3", "language": "vi", "response_format": "verbose_json"}, 
                        timeout=180
                    )
                
                if res.status_code == 200:
                    # Gộp text liền mạch không cần timestamp
                    text_content = " ".join([s['text'].strip() for s in res.json().get("segments", [])])
                    with open(txt_output, "w", encoding="utf-8") as f: f.write(text_content)
                    
                    self.ui.add_log(f"✅ LƯU THÀNH CÔNG: {os.path.basename(txt_output)}")
                    self.ui.main_app.root.after(0, self.ui.safe_update_listbox)
                    return True
                else:
                    raise Exception(f"Lỗi Groq: {res.text[:100]}")

            else:
                # =======================================================
                # [BẢN NÂNG CẤP] CHẾ ĐỘ OHFREE + GOOGLE DRIVE (TỰ XIN TOKEN)
                # =======================================================
                self.ui.add_log(f"[{index+1}] Đang kiểm tra quyền Drive & Bóc bằng OhFree...")
                
                from google_auth_oauthlib.flow import InstalledAppFlow
                from google.auth.transport.requests import Request
                from google.oauth2.credentials import Credentials

                SCOPES = ['https://www.googleapis.com/auth/drive.file']
                token_path = os.path.join(os.getcwd(), 'token.json')
                creds = None

                # 1. Thử đọc file token cũ
                if os.path.exists(token_path):
                    try:
                        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                    except:
                        pass

                # 2. Nếu thẻ mất hoặc hỏng -> Tự động bật Web xin thẻ mới
                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    else:
                        # Bật trình duyệt để sếp chọn Gmail (Cần file credentials.json nằm cạnh file main.py)
                        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                        creds = flow.run_local_server(port=0)
                    
                    # Xin được rồi thì lưu lại thành file token.json để lần sau dùng tiếp
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())

                # 3. Kết nối dịch vụ Drive
                drive_service = build('drive', 'v3', credentials=creds)

                # --- Tiếp tục quy trình đẩy file lên Drive cũ của sếp ---
                file_metadata = {'name': f"audio_{index}.mp3", 'parents': [self.folder_id]}
                file = drive_service.files().create(
                    body=file_metadata, 
                    media_body=MediaFileUpload(temp_audio, mimetype='audio/mpeg'), 
                    fields='id'
                ).execute()
                
                file_id = file.get('id')
                # Cấp quyền xem công khai để OhFree đọc được link
                drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()

                # --- Đoạn gọi API OhFree giữ nguyên như cũ ---
                headers = {
                    "User-Agent": "Mozilla/5.0...", 
                    "Origin": "https://tts.ohfree.me",
                    "Cookie": cookie
                }
                # ... (Các phần còn lại giữ nguyên)
                
                res = requests.post(
                    "https://tts.ohfree.me/api/mp3-to-text", 
                    headers=headers, 
                    files={'url': (None, f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link")}, 
                    timeout=300
                )
                
                if res.status_code == 200 and res.json().get('success'):
                    self.json_to_flat_text(res.json().get('data', {}).get('words', []), txt_output)
                    self.ui.add_log(f"✅ LƯU THÀNH CÔNG: {os.path.basename(txt_output)}")
                    self.ui.main_app.root.after(0, self.ui.safe_update_listbox)
                    return True
                else: 
                    raise Exception(f"OhFree từ chối (Mã lỗi: {res.status_code}) - Chi tiết: {res.text[:100]}")

        except Exception as e:
            self.ui.add_log(f"❌ [Luồng {index+1}] Lỗi: {str(e)}")
            return False
            
        finally:
            # Quét rác
            for f in [temp_video, temp_audio]:
                if f and os.path.exists(f):
                    try: os.remove(f)
                    except: pass
            if file_id and drive_service:
                try: drive_service.files().delete(fileId=file_id).execute()
                except: pass