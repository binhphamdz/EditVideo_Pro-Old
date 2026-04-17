import tkinter as tk
from tkinter import ttk, messagebox

class ConfigTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.setup_ui()

    def setup_ui(self):
        # Khung chứa chính
        container = tk.Frame(self.parent, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        title = tk.Label(container, text="⚙️ QUẢN TRỊ VIÊN: CẤU HÌNH KEY & COOKIES", 
                         font=("Arial", 15, "bold"), bg="#f4f6f9", fg="#2c3e50")
        title.pack(pady=(0, 20))

        # --- KHU VỰC CÁC LOẠI KEY ---
        key_frame = tk.LabelFrame(container, text=" 🔑 Danh Sách API Keys ", 
                                  font=("Arial", 11, "bold"), bg="#ffffff", padx=15, pady=15)
        key_frame.pack(fill="x", pady=10)

        self.entries = {}

        # Danh sách các cấu hình cần quản lý
        fields = [
            ("groq_key", "🚀 Groq API Key (Tab 2/7/Bot):"),
            ("kie_key", "🧠 Kie AI Key (Tab 2/7/9):"),
            ("telegram_bot_token", "🤖 Telegram Bot Token:"),
            ("gemini_key", "💎 Gemini AI Key (Dự phòng):"),
        ]

        for key, label in fields:
            row = tk.Frame(key_frame, bg="#ffffff")
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, width=25, anchor="w", bg="#ffffff", font=("Arial", 10)).pack(side="left")
            
            # Entry có chế độ ẩn/hiện key
            ent = tk.Entry(row, font=("Consolas", 11), show="*")
            ent.insert(0, self.main_app.config.get(key, ""))
            ent.pack(side="left", fill="x", expand=True, padx=5)
            
            btn_show = tk.Button(row, text="👁️", width=3, command=lambda e=ent: self.toggle_eye(e))
            btn_show.pack(side="right")
            self.entries[key] = ent

        # --- KHU VỰC COOKIES & ĐƯỜNG DẪN ---
        other_frame = tk.LabelFrame(container, text=" 🍪 Cookies & Hệ Thống ", 
                                     font=("Arial", 11, "bold"), bg="#ffffff", padx=15, pady=15)
        other_frame.pack(fill="x", pady=10)

        # OhFree Cookie
        row_c = tk.Frame(other_frame, bg="#ffffff")
        row_c.pack(fill="x", pady=5)
        tk.Label(row_c, text="🍪 OhFree Cookie (Tab 6/7):", width=25, anchor="w", bg="#ffffff", font=("Arial", 10)).pack(side="left")
        self.txt_cookie = tk.Text(row_c, height=4, font=("Consolas", 9))
        self.txt_cookie.insert("1.0", self.main_app.config.get("ohfree_cookie", ""))
        self.txt_cookie.pack(side="left", fill="x", expand=True, padx=5)

        # iCloud Path
        row_i = tk.Frame(other_frame, bg="#ffffff")
        row_i.pack(fill="x", pady=5)
        tk.Label(row_i, text="☁️ Đường dẫn iCloud:", width=25, anchor="w", bg="#ffffff", font=("Arial", 10)).pack(side="left")
        self.ent_icloud = tk.Entry(row_i, font=("Arial", 10))
        self.ent_icloud.insert(0, self.main_app.config.get("icloud_path", ""))
        self.ent_icloud.pack(side="left", fill="x", expand=True, padx=5)

        # Nút Lưu
        btn_save = tk.Button(container, text="💾 LƯU TẤT CẢ CẤU HÌNH", bg="#27ae60", fg="white", 
                             font=("Arial", 12, "bold"), pady=10, command=self.save_all_config)
        btn_save.pack(fill="x", pady=20)

    def toggle_eye(self, entry):
        if entry.cget("show") == "*":
            entry.config(show="")
        else:
            entry.config(show="*")

    def save_all_config(self):
        # Thu thập dữ liệu
        for key, entry in self.entries.items():
            self.main_app.config[key] = entry.get().strip()
        
        self.main_app.config["ohfree_cookie"] = self.txt_cookie.get("1.0", tk.END).strip()
        self.main_app.config["icloud_path"] = self.ent_icloud.get().strip()

        # Lưu vào file JSON
        self.main_app.save_config()
        messagebox.showinfo("Thành công", "Đã cập nhật toàn bộ Key và Cookies vào hệ thống!")
        
        # [QUAN TRỌNG] Đồng bộ ngay lập tức sang các Tab khác nếu chúng đang mở
        self.sync_to_other_tabs()

    def sync_to_other_tabs(self):
        """ Ép các tab khác cập nhật lại giá trị hiển thị trên màn hình """
        try:
            # Cập nhật Tab 2
            self.main_app.tab2.ent_groq.delete(0, tk.END)
            self.main_app.tab2.ent_groq.insert(0, self.main_app.config.get("groq_key", ""))
            self.main_app.tab2.ent_kie.delete(0, tk.END)
            self.main_app.tab2.ent_kie.insert(0, self.main_app.config.get("kie_key", ""))
            
            # Cập nhật Tab 7
            self.main_app.tab7.ent_kie.delete(0, tk.END)
            self.main_app.tab7.ent_kie.insert(0, self.main_app.config.get("kie_key", ""))
            
            # Cập nhật Tab 6 (Cookie)
            self.main_app.tab6.ent_cookie.delete(0, tk.END)
            self.main_app.tab6.ent_cookie.insert(0, self.main_app.config.get("ohfree_cookie", ""))
        except:
            pass