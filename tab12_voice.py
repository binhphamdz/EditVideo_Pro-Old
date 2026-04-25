import os
import requests
import threading
import tkinter as tk
from tkinter import ttk, messagebox

class TabVoice:
    def __init__(self, master, parent_app):
        self.master = master
        self.parent_app = parent_app 
        
        # ID Voice sếp yêu cầu
        self.default_speaker_id = "voice-02a1e0b5-bafd-497c"
        
        self.setup_ui()

    def setup_ui(self):
        # 1. Ô nhập API Key
        key_frame = tk.Frame(self.master)
        key_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(key_frame, text="EverAI API Key:", font=("Arial", 10, "bold")).pack(side="left")
        self.api_key_entry = ttk.Entry(key_frame, width=50)
        self.api_key_entry.pack(side="left", padx=10)
        self.api_key_entry.insert(0, "Dán API Key vào đây...")

        # 2. Ô nhập văn bản
        tk.Label(self.master, text="Nội dung muốn chuyển thành giọng nói:", font=("Arial", 12, "bold")).pack(anchor="w", padx=20, pady=(10, 0))
        self.text_input = tk.Text(self.master, height=15, wrap="word", font=("Arial", 11))
        self.text_input.pack(fill="both", expand=True, padx=20, pady=5)

        # 3. Điều chỉnh thông số
        ctrl_frame = tk.Frame(self.master)
        ctrl_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(ctrl_frame, text="Tốc độ đọc:", font=("Arial", 10, "bold")).pack(side="left")
        self.speed_slider = tk.Scale(ctrl_frame, from_=0.5, to=2.0, resolution=0.1, orient="horizontal", length=200)
        self.speed_slider.set(1.0) # Tốc độ mặc định
        self.speed_slider.pack(side="left", padx=10)

        # 4. Nút bấm
        self.btn_generate = tk.Button(self.master, text="🚀 BẮT ĐẦU CHUYỂN VOICE", font=("Arial", 14, "bold"), 
                                      bg="#4CAF50", fg="white", height=2, command=self.start_generate_thread)
        self.btn_generate.pack(fill="x", padx=20, pady=20)

    def start_generate_thread(self):
        # Chạy API trên một luồng (thread) riêng để giao diện không bị đơ
        api_key = self.api_key_entry.get().strip()
        content = self.text_input.get("1.0", "end-1c").strip()
        
        if not api_key or api_key == "Dán API Key vào đây...":
            messagebox.showwarning("Thiếu thông tin", "Sếp chưa nhập API Key!")
            return
            
        if not content:
            messagebox.showwarning("Thiếu thông tin", "Sếp chưa nhập nội dung!")
            return

        self.btn_generate.config(state="disabled", text="⌛ ĐANG XỬ LÝ LÊN MÂY...", bg="#9E9E9E")
        
        # Bắt đầu luồng phụ
        threading.Thread(target=self._process_api, args=(api_key, content), daemon=True).start()

    def _process_api(self, api_key, content):
        import time # Cần import thêm time để chờ API
        
        url_post = "https://everai.vn/api/v1/tts"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # 1. Định dạng payload chuẩn 100% theo Document của EverAI
        payload = {
            "response_type": "indirect",
            "callback_url": "https://webhook.site/dummy", # Truyền dummy để lách luật
            "input_text": content,
            "voice_code": self.default_speaker_id, # Ví dụ: "voice-02a1e0b5-bafd-497c"
            "audio_type": "mp3",
            "speed_rate": self.speed_slider.get()
        }

        try:
            # BƯỚC 1: Gửi kịch bản lên để xếp hàng
            response = requests.post(url_post, json=payload, headers=headers)
            if response.status_code != 200:
                self.master.after(0, lambda: messagebox.showerror("Lỗi API", f"Lỗi kết nối Server: {response.text}"))
                return
                
            res_json = response.json()
            if res_json.get("status") != 1:
                error_msg = res_json.get("error_message", "Lỗi không xác định")
                self.master.after(0, lambda: messagebox.showerror("Lỗi EverAI", f"EverAI từ chối: {error_msg}"))
                return
                
            # Lấy mã vé xếp hàng
            request_id = res_json["result"]["request_id"]
            
            # BƯỚC 2: Liên tục hỏi xem nó đã ghép giọng xong chưa (Polling)
            url_get = f"https://everai.vn/api/v1/tts/{request_id}"
            audio_link = None
            
            for _ in range(60): # Chờ tối đa 2 phút (60 lần x 2 giây)
                time.sleep(2) # Nghỉ 2 giây rồi hỏi tiếp để tránh bị khóa IP
                
                check_resp = requests.get(url_get, headers=headers)
                if check_resp.status_code == 200:
                    check_data = check_resp.json()
                    status = check_data["result"]["status"]
                    
                    if status == "done": # Render xong!
                        audio_link = check_data["result"]["audio_link"]
                        break
                    elif status in ["error", "failed"]:
                        self.master.after(0, lambda: messagebox.showerror("Lỗi Server", "EverAI bị lỗi khi ghép giọng này!"))
                        return
            
            if not audio_link:
                self.master.after(0, lambda: messagebox.showerror("Quá giờ", "Chờ EverAI quá lâu, sếp thử lại sau nhé!"))
                return
                
            # BƯỚC 3: Tải file mp3 về máy của sếp
            audio_data = requests.get(audio_link).content
            save_path = os.path.join(os.getcwd(), "output_voice.mp3")
            
            with open(save_path, "wb") as f:
                f.write(audio_data)
            
            # Báo thành công
            self.master.after(0, lambda: messagebox.showinfo("Thành công rực rỡ", f"Voice đã được kéo về tại:\n{save_path}"))
            
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Lỗi hệ thống", f"Vấp dây mạng rồi: {str(e)}"))
        finally:
            # Phục hồi nút bấm
            self.master.after(0, lambda: self.btn_generate.config(state="normal", text="🚀 BẮT ĐẦU CHUYỂN VOICE", bg="#4CAF50"))