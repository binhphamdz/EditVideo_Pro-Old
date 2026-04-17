import os
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
from datetime import datetime
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed 

# Import vũ khí hạt nhân
try:
    import yt_dlp
    HAS_YTDLP = True
except ImportError:
    HAS_YTDLP = False

class TikTokTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.setup_ui()

    def setup_ui(self):
        tk.Label(self.parent, text="🎵 MÁY HÚT TIKTOK (TÍCH HỢP YT-DLP)", font=("Arial", 14, "bold"), bg="#f4f6f9", fg="#2980b9").pack(pady=(20, 10))

        # --- KHUNG 1: NHẬP LINK ---
        input_fr = tk.LabelFrame(self.parent, text=" 1. Dán Danh Sách Link (Mỗi link 1 dòng) ", font=("Arial", 10, "bold"), bg="#ffffff", padx=15, pady=10)
        input_fr.pack(fill="x", padx=20, pady=5)

        self.txt_urls = tk.Text(input_fr, height=6, font=("Arial", 10), bg="#fdfdfd")
        self.txt_urls.pack(fill="x", pady=5)

        # --- KHUNG 2: CẤU HÌNH LUỒNG & CHỌN VŨ KHÍ ---
        config_fr = tk.Frame(self.parent, bg="#f4f6f9")
        config_fr.pack(fill="x", padx=20, pady=5)

        tk.Label(config_fr, text="Số luồng hút:", font=("Arial", 10, "bold"), bg="#f4f6f9").pack(side="left")
        self.spin_threads = tk.Spinbox(config_fr, from_=1, to=10, width=5, font=("Arial", 10, "bold"))
        self.spin_threads.insert(0, "5") 
        self.spin_threads.pack(side="left", padx=10)

        # TÙY CHỌN: CHỌN ĐỘNG CƠ TẢI
        self.use_ytdlp = tk.BooleanVar(value=HAS_YTDLP) # Mặc định tick nếu máy đã cài yt-dlp
        chk_ytdlp = tk.Checkbutton(config_fr, text="🔥 Dùng lõi yt-dlp (Không bị giới hạn tốc độ)", variable=self.use_ytdlp, font=("Arial", 10, "bold"), bg="#f4f6f9", fg="#c0392b")
        chk_ytdlp.pack(side="left", padx=20)
        if not HAS_YTDLP:
            chk_ytdlp.config(state="disabled", text="❌ Lõi yt-dlp chưa cài (Hãy gõ: pip install yt-dlp)")

        # --- KHUNG 3: ĐIỀU KHIỂN & TRẠNG THÁI ---
        action_fr = tk.Frame(self.parent, bg="#f4f6f9")
        action_fr.pack(fill="x", padx=20, pady=5)

        self.btn_download = tk.Button(action_fr, text="📥 HÚT TOÀN BỘ VIDEO", bg="#27ae60", fg="white", font=("Arial", 12, "bold"), pady=8, command=self.start_download)
        self.btn_download.pack(fill="x", pady=(0, 10))

        # --- KHUNG 4: NHẬT KÝ ---
        log_fr = tk.LabelFrame(self.parent, text=" 2. Nhật Ký Hoạt Động ", font=("Arial", 10, "bold"), bg="#ffffff", padx=15, pady=10)
        log_fr.pack(fill="both", expand=True, padx=20, pady=5)

        self.txt_log = tk.Text(log_fr, bg="#1e272e", fg="#2ecc71", font=("Consolas", 10), state="disabled", height=10)
        self.txt_log.pack(fill="both", expand=True)

        bot_fr = tk.Frame(self.parent, bg="#f4f6f9")
        bot_fr.pack(fill="x", padx=20, pady=10)
        tk.Button(bot_fr, text="📂 Mở Thư Mục Chứa Video", bg="#34495e", fg="white", font=("Arial", 10, "bold"), command=self.open_folder).pack(side="right")

    def add_log(self, msg):
        self.main_app.root.after(0, self._insert_log, msg)

    def _insert_log(self, msg):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def clean_filename(self, title):
        clean = re.sub(r'[\\/*?:"<>|]', "", title)
        return clean[:50].strip()

    def start_download(self):
        raw_urls = self.txt_urls.get("1.0", tk.END).splitlines()
        valid_urls = [u.strip() for u in raw_urls if "tiktok.com" in u.strip()]

        if not valid_urls:
            return messagebox.showwarning("Chú ý", "Bác chưa dán link hợp lệ nào (mỗi link 1 dòng nhé)!")

        try:
            threads = int(self.spin_threads.get())
            if threads > 20: threads = 20 
        except:
            threads = 5

        engine_name = "yt-dlp" if self.use_ytdlp.get() else "TikWM"
        self.btn_download.config(state="disabled", text=f"⏳ ĐANG HÚT {len(valid_urls)} VIDEO BẰNG {engine_name.upper()}...", bg="#7f8c8d")
        
        threading.Thread(target=self._process_batch, args=(valid_urls, threads), daemon=True).start()

    def _process_batch(self, urls, max_workers):
        self.add_log(f"🚀 Bắt đầu chiến dịch hút {len(urls)} video với {max_workers} luồng song song!")
        
        success_count = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self._download_single, url, index): url for index, url in enumerate(urls)}
            
            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    res = future.result()
                    if res: success_count += 1
                except Exception as e:
                    self.add_log(f"❌ Lỗi ngoài ý muốn với link {url[:30]}... : {e}")

        self.add_log(f"🎉 CHIẾN DỊCH HOÀN TẤT! Đã vác về kho {success_count}/{len(urls)} video.")
        self.main_app.root.after(0, lambda: self.btn_download.config(state="normal", text="📥 HÚT TOÀN BỘ VIDEO", bg="#27ae60"))

    def _download_single(self, url, index):
        save_dir = os.path.join(os.getcwd(), "TikTok_Downloads")
        os.makedirs(save_dir, exist_ok=True)
        
        is_success = False

        # ========================================================
        # BƯỚC 1: XUNG PHONG BẰNG YT-DLP (SIÊU TỐC)
        # ========================================================
        if self.use_ytdlp.get():
            try:
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]', 
                    'merge_output_format': 'mp4',
                    'outtmpl': os.path.join(save_dir, '%(title).50s_[%(id)s].%(ext)s'),
                    'quiet': True,
                    'no_warnings': True,
                    'nocheckcertificate': True
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    # Nếu là slideshow hoặc chỉ có audio -> Đẩy sang TikWM
                    if info.get('vcodec') == 'none' and not info.get('requested_formats'):
                        raise Exception("Giỏ Hàng/Slideshow")
                        
                    ydl.download([url])
                    downloaded_file = ydl.prepare_filename(info)
                    
                self.add_log(f"✅ XONG (yt-dlp): {os.path.basename(downloaded_file)}")
                return True
            except Exception:
                self.add_log(f"⚠️ [Bẻ Lái] yt-dlp đụng Giỏ Hàng, đẩy link sang TikWM: {url[:20]}...")
                is_success = False

        # ========================================================
        # BƯỚC 2: TIKWM BỌC HẬU (CHIẾN THUẬT LÌ ĐÒN 5 LẦN)
        # ========================================================
        if not is_success:
            # Nghỉ ban đầu để giãn cách luồng
            time.sleep(index * 1.5)
            
            max_retries = 5 # NÂNG CẤP LÊN 5 LẦN THỬ LẠI
            for attempt in range(max_retries):
                try:
                    api_url = "https://www.tikwm.com/api/"
                    payload = {"url": url, "count": 12, "cursor": 0, "web": 1, "hd": 1}
                    
                    res = requests.post(api_url, data=payload, timeout=20) 
                    
                    if res.status_code != 200:
                        raise Exception("Server TikWM ngâm kết nối.")
                    
                    data = res.json()
                    if data.get("code") != 0:
                        error_msg = data.get("msg", "Link sai hoặc video riêng tư.")
                        raise Exception(error_msg)

                    vid_data = data.get("data", {})
                    play_url = vid_data.get("play")
                    title = vid_data.get("title", "TikTok_Video")
                    
                    if not play_url:
                        raise Exception("Không tìm thấy link MP4.")

                    if play_url.startswith("/"):
                        play_url = "https://www.tikwm.com" + play_url

                    safe_title = self.clean_filename(title)
                    if not safe_title: safe_title = f"Video_{datetime.now().strftime('%H%M%S_%f')}" 
                    
                    file_name = f"{safe_title}.mp4"
                    save_path = os.path.join(save_dir, file_name)

                    base_name, ext = os.path.splitext(file_name)
                    counter = 1
                    while os.path.exists(save_path):
                        file_name = f"{base_name}_{counter}{ext}"
                        save_path = os.path.join(save_dir, file_name)
                        counter += 1

                    vid_res = requests.get(play_url, stream=True, timeout=30)
                    if vid_res.status_code == 200:
                        with open(save_path, 'wb') as f:
                            for chunk in vid_res.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        
                        self.add_log(f"✅ XONG (TikWM): {file_name[:40]}...")
                        return True
                    else:
                        raise Exception(f"Lỗi kéo MP4 (HTTP {vid_res.status_code})")

                except Exception as e:
                    err_str = str(e)
                    # NẾU DÍNH LỖI GIỚI HẠN 1s -> CHỜ 3 GIÂY RỒI ĐÂM LẠI
                    if "1 request/second" in err_str and attempt < max_retries - 1:
                        self.add_log(f"⚠️ [Thử {attempt+1}/5] Nghẽn TikWM, nghỉ 3s rồi múc lại: {url[:25]}...")
                        time.sleep(3) # Nghỉ lâu hơn cho chắc
                        continue 
                    
                    # Nếu là lỗi khác hoặc đã thử 5 lần vẫn xịt
                    self.add_log(f"❌ THẤT BẠI ({url[:30]}...): {e}")
                    return False
                
    def open_folder(self):
        save_dir = os.path.join(os.getcwd(), "TikTok_Downloads")
        os.makedirs(save_dir, exist_ok=True)
        os.startfile(save_dir)