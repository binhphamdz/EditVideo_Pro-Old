import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time

class TelegramTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.setup_ui()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        container = tk.Frame(self.parent, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Tiêu đề
        tk.Label(
            container, 
            text="🤖 CẤU HÌNH BOT TELEGRAM ĐIỀU KHIỂN TỪ XA", 
            font=("Arial", 15, "bold"), 
            bg="#f4f6f9", 
            fg="#2980b9"
        ).pack(pady=(0, 20))

        # Khung cài đặt Token
        frame_config = tk.LabelFrame(container, text=" 🔑 Kết nối Bot Telegram ", font=("Arial", 11, "bold"), bg="#ffffff", padx=20, pady=20)
        frame_config.pack(fill="x", pady=10)

        tk.Label(frame_config, text="Mã Token của Bot:", font=("Arial", 11), bg="#ffffff").grid(row=0, column=0, sticky="w", pady=10)
        
        # Ô nhập Token
        self.entry_token = tk.Entry(frame_config, font=("Arial", 11), width=55, show="*")
        self.entry_token.grid(row=0, column=1, padx=10, pady=10)
        
        # Nút hiện/ẩn Token
        self.show_token_var = tk.BooleanVar()
        tk.Checkbutton(frame_config, text="Hiện", variable=self.show_token_var, bg="#ffffff", command=self.toggle_token_visibility).grid(row=0, column=2)

        # Trạng thái Bot
        tk.Label(frame_config, text="Trạng thái:", font=("Arial", 11), bg="#ffffff").grid(row=1, column=0, sticky="w", pady=10)
        self.lbl_status = tk.Label(frame_config, text="Chưa kết nối", font=("Arial", 11, "bold"), fg="#e74c3c", bg="#ffffff")
        self.lbl_status.grid(row=1, column=1, sticky="w", padx=10, pady=10)

        # Các nút thao tác
        btn_frame = tk.Frame(frame_config, bg="#ffffff")
        btn_frame.grid(row=2, column=0, columnspan=3, pady=15)

        tk.Button(btn_frame, text="💾 Lưu Lại & Khởi Động Bot", bg="#27ae60", fg="white", font=("Arial", 11, "bold"), padx=15, pady=5, command=self.save_and_restart_bot).pack(side="left", padx=10)
        tk.Button(btn_frame, text="🛑 Tắt Bot", bg="#c0392b", fg="white", font=("Arial", 11, "bold"), padx=15, pady=5, command=self.stop_bot).pack(side="left", padx=10)

        # Khung Hướng dẫn
        frame_guide = tk.LabelFrame(container, text=" 📖 Hướng dẫn tạo Bot ", font=("Arial", 11, "bold"), bg="#ffffff", padx=20, pady=15)
        frame_guide.pack(fill="both", expand=True, pady=10)

        guide_text = """
1. Mở ứng dụng Telegram, tìm kiếm: @BotFather
2. Bấm Start, sau đó nhắn lệnh: /newbot
3. Đặt Tên hiển thị cho Bot (Ví dụ: Trạm Kiểm Soát Video)
4. Đặt Username cho Bot (Bắt buộc kết thúc bằng chữ 'bot', Ví dụ: ToolEditPro_bot)
5. Copy đoạn mã màu đỏ (Token) ở tin nhắn cuối cùng dán vào ô bên trên.
6. Quay lại Telegram, tìm con Bot vừa tạo, bấm /start để bắt đầu sử dụng.

Lệnh điều khiển hiện tại:
- /icloud : Quét các video chưa chuyển và bắn sang iCloud Drive.
        """
        tk.Label(frame_guide, text=guide_text, font=("Arial", 11), bg="#ffffff", justify="left").pack(anchor="w")

        # Nạp dữ liệu cũ lúc bật Tool
        self.load_current_config()
        self.update_status_ui()

    def toggle_token_visibility(self):
        if self.show_token_var.get():
            self.entry_token.config(show="")
        else:
            self.entry_token.config(show="*")

    def load_current_config(self):
        token = self.main_app.config.get("telegram_bot_token", "")
        if token:
            self.entry_token.insert(0, token)

    def update_status_ui(self):
        # Kiểm tra xem bot trong main_app có đang chạy không
        if self.main_app.bot_is_running:
            self.lbl_status.config(text="🟢 Đang chạy & Sẵn sàng nhận lệnh", fg="#27ae60")
        else:
            self.lbl_status.config(text="🔴 Đang tắt", fg="#c0392b")
        # 1 giây sau tự động check lại trạng thái
        self.parent.after(1000, self.update_status_ui)

    def save_and_restart_bot(self):
        token = self.entry_token.get().strip()
        if not token:
            messagebox.showwarning("Lỗi", "Bác chưa nhập Token kìa!")
            return

        # Lưu vào file config
        self.main_app.config["telegram_bot_token"] = token
        self.main_app.save_config()

        # Ra lệnh cho main_app khởi động lại Bot
        self.main_app.restart_telegram_bot()
        messagebox.showinfo("Thành công", "Đã lưu Token và kích hoạt Bot!")

    def stop_bot(self):
        self.main_app.stop_telegram_bot()
        messagebox.showinfo("Đã tắt", "Đã tắt Bot Telegram!")