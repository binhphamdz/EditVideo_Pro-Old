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

    # [BẢN ĐỘ MỚI] - HÀM ĐẶT TÊN ĐỘNG DỰA TRÊN KỊCH BẢN
    def save_dynamic_script(self, text_content, url, target_dir):
        # 1. Trích xuất username từ URL (vd: namoinam)
        username = "TikTok"
        match = re.search(r'@([\w\.-]+)', url)
        if match:
            username = match.group(1)

        # 2. Lấy 6 từ đầu tiên của kịch bản làm tên, bỏ hết các ký tự cấm của Windows
        clean_text = re.sub(r'[\\/*?:"<>|\n\t]', " ", text_content).strip()
        words = clean_text.split()[:6] 
        first_part = "_".join(words)
        if not first_part:
            first_part = "Khong_Co_Loi_Thoai"

        # 3. Tạo 5 số ngẫu nhiên tránh trùng lặp
        rand_nums = str(random.randint(10000, 99999))

        # 4. Gắn tên (BẮT BUỘC có chữ KB_ ở đầu vì Tab 7 chỉ nhận diện file KB_)
        final_name = f"KB_{username}_{first_part}_{rand_nums}.txt"
        final_path = os.path.join(target_dir, final_name)

        # Lưu file
        with open(final_path, "w", encoding="utf-8") as f: 
            f.write(text_content)

        return final_name

    # Đã sửa lại để hàm này chỉ trả về Text chứ không lưu thẳng file nữa
    def get_flat_text(self, words_list):
        return " ".join([w.get('word', '').strip() for w in words_list if w.get('word', '').strip() not in ['<start>', '<end>', '']])

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

            video = VideoFileClip(temp_video)
            video.audio.write_audiofile(temp_audio, logger=None)
            video.close()

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
                    text_content = " ".join([s['text'].strip() for s in res.json().get("segments", [])])
                    
                    # [MỚI] Gọi hàm tạo tên động và lưu file
                    final_filename = self.save_dynamic_script(text_content, url, target_dir)
                    
                    self.ui.add_log(f"✅ LƯU THÀNH CÔNG: {final_filename}")
                    self.ui.main_app.root.after(0, self.ui.safe_update_listbox)
                    return True
                else:
                    raise Exception(f"Lỗi Groq: {res.text[:100]}")

            else:
                self.ui.add_log(f"[{index+1}] Đang kiểm tra quyền Drive & Bóc bằng OhFree...")
                
                from google_auth_oauthlib.flow import InstalledAppFlow
                from google.auth.transport.requests import Request
                from google.oauth2.credentials import Credentials

                SCOPES = ['https://www.googleapis.com/auth/drive.file']
                token_path = os.path.join(os.getcwd(), 'token.json')
                creds = None

                if os.path.exists(token_path):
                    try:
                        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                    except: pass

                if not creds or not creds.valid:
                    if creds and creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                    else:
                        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                        creds = flow.run_local_server(port=0)
                    with open(token_path, 'w') as token:
                        token.write(creds.to_json())

                drive_service = build('drive', 'v3', credentials=creds)

                file_metadata = {'name': f"audio_{index}.mp3", 'parents': [self.folder_id]}
                file = drive_service.files().create(
                    body=file_metadata, 
                    media_body=MediaFileUpload(temp_audio, mimetype='audio/mpeg'), 
                    fields='id'
                ).execute()
                
                file_id = file.get('id')
                drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()

                headers = {
                    "User-Agent": "Mozilla/5.0...", 
                    "Origin": "https://tts.ohfree.me",
                    "Cookie": cookie
                }
                
                res = requests.post(
                    "https://tts.ohfree.me/api/mp3-to-text", 
                    headers=headers, 
                    files={'url': (None, f"https://drive.google.com/file/d/{file_id}/view?usp=drive_link")}, 
                    timeout=300
                )
                
                if res.status_code == 200 and res.json().get('success'):
                    text_content = self.get_flat_text(res.json().get('data', {}).get('words', []))
                    
                    # [MỚI] Gọi hàm tạo tên động và lưu file
                    final_filename = self.save_dynamic_script(text_content, url, target_dir)
                    
                    self.ui.add_log(f"✅ LƯU THÀNH CÔNG: {final_filename}")
                    self.ui.main_app.root.after(0, self.ui.safe_update_listbox)
                    return True
                else: 
                    raise Exception(f"OhFree từ chối (Mã lỗi: {res.status_code}) - Chi tiết: {res.text[:100]}")

        except Exception as e:
            self.ui.add_log(f"❌ [Luồng {index+1}] Lỗi: {str(e)}")
            return False
            
        finally:
            for f in [temp_video, temp_audio]:
                if f and os.path.exists(f):
                    try: os.remove(f)
                    except: pass
            if file_id and drive_service:
                try: drive_service.files().delete(fileId=file_id).execute()
                except: pass