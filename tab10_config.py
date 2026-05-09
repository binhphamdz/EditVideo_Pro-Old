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
            ("kie_key", "🧠 Kie AI Key (Tab 1/2/7):"),
            ("openai_key", "🤖 OpenAI API Key (ChatGPT):"),
            ("shopaikey_key", "🌟 ShopAIKey API Key (Gemini Flash):"),
            ("telegram_bot_token", "📱 Telegram Bot Token:"),
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

        # --- CẤU HÌNH AI PROVIDER ---
        ai_config_fr = tk.LabelFrame(container, text=" 🤖 Cấu Hình AI Provider ", 
                                     font=("Arial", 11, "bold"), bg="#ffffff", padx=15, pady=15)
        ai_config_fr.pack(fill="x", pady=10)

        # AI Provider Selector
        row_provider = tk.Frame(ai_config_fr, bg="#ffffff")
        row_provider.pack(fill="x", pady=5)
        tk.Label(row_provider, text="AI Provider (Tab 1/2/7):", width=25, anchor="w", bg="#ffffff", font=("Arial", 10, "bold"), fg="#e74c3c").pack(side="left")
        
        self.ai_provider = tk.StringVar(value=self.main_app.config.get("ai_provider", "kie"))
        tk.Radiobutton(row_provider, text="Kie.ai (Miễn phí)", variable=self.ai_provider, value="kie", bg="#ffffff", font=("Arial", 10)).pack(side="left", padx=10)
        tk.Radiobutton(row_provider, text="OpenAI (ChatGPT)", variable=self.ai_provider, value="openai", bg="#ffffff", font=("Arial", 10)).pack(side="left")
        tk.Radiobutton(row_provider, text="ShopAIKey (Gemini Flash)", variable=self.ai_provider, value="shopaikey", bg="#ffffff", font=("Arial", 10)).pack(side="left", padx=10)

        # Kie Model Selector
        row_kie = tk.Frame(ai_config_fr, bg="#ffffff")
        row_kie.pack(fill="x", pady=5)
        tk.Label(row_kie, text="Kie Model:", width=25, anchor="w", bg="#ffffff", font=("Arial", 10)).pack(side="left")

        self.cb_kie = ttk.Combobox(row_kie, state="readonly", font=("Arial", 10), width=22)
        self.cb_kie['values'] = ["gemini-3-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
        saved_kie = self.main_app.config.get("kie_model", "gemini-3-flash")
        if saved_kie in self.cb_kie['values']:
            self.cb_kie.set(saved_kie)
        else:
            self.cb_kie.current(0)
        self.cb_kie.pack(side="left", padx=5)

        tk.Label(row_kie, text="(Gemini Flash 2-3)", bg="#ffffff", font=("Arial", 9, "italic"), fg="#7f8c8d").pack(side="left", padx=10)

        # OpenAI Model Selector
        row_model = tk.Frame(ai_config_fr, bg="#ffffff")
        row_model.pack(fill="x", pady=5)
        tk.Label(row_model, text="OpenAI Model:", width=25, anchor="w", bg="#ffffff", font=("Arial", 10)).pack(side="left")
        
        self.cb_model = ttk.Combobox(row_model, state="readonly", font=("Arial", 10), width=20)
        self.cb_model['values'] = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "gpt-3.5-turbo-16k"]
        saved_model = self.main_app.config.get("openai_model", "gpt-4o")
        if saved_model in self.cb_model['values']:
            self.cb_model.set(saved_model)
        else:
            self.cb_model.current(0)
        self.cb_model.pack(side="left", padx=5)
        
        tk.Label(row_model, text="(Khuyến nghị: gpt-4o-mini)", bg="#ffffff", font=("Arial", 9, "italic"), fg="#7f8c8d").pack(side="left", padx=10)

        # Gemini Model Selector (ShopAIKey)
        row_gemini = tk.Frame(ai_config_fr, bg="#ffffff")
        row_gemini.pack(fill="x", pady=5)
        tk.Label(row_gemini, text="Gemini Model:", width=25, anchor="w", bg="#ffffff", font=("Arial", 10)).pack(side="left")

        self.cb_gemini = ttk.Combobox(row_gemini, state="readonly", font=("Arial", 10), width=60)
        self.gemini_model_options = [
            ("gemini-3.1-flash-tts-preview:generateContent", "gemini-3.1-flash-tts-preview (tts) | IN $1.50 OUT $30.00 | VND 4875/97500"),
            ("gemini-3.1-flash-lite-preview:generateContent", "gemini-3.1-flash-lite-preview | IN $0.38 OUT $2.25 | VND 1218.75/7312.5"),
            ("gemini-3.1-pro-preview:generateContent", "gemini-3.1-pro-preview | IN $3.00 OUT $18.00 | VND 9750/58500"),
            ("gemini-3.1-flash-image-preview:generateContent", "gemini-3.1-flash-image-preview (image) | PER $0.2483 | VND 806.813"),
            ("gemini-3-pro-image-preview:generateContent", "gemini-3-pro-image-preview (image) | PER $0.4950 | VND 1608.75"),
            ("gemini-3-pro-preview:generateContent", "gemini-3-pro-preview | IN $3.00 OUT $18.00 | VND 9750/58500"),
            ("gemini-3-flash-preview:generateContent", "gemini-3-flash-preview | IN $0.75 OUT $4.50 | VND 2437.5/14625"),
            ("gemini-2.5-flash-preview-tts:generateContent", "gemini-2.5-flash-preview-tts (tts) | IN $0.75 OUT $15.00 | VND 2437.5/48750"),
            ("gemini-2.5-pro-preview-tts:generateContent", "gemini-2.5-pro-preview-tts (tts) | IN $1.50 OUT $30.00 | VND 4875/97500"),
            ("gemini-3-pro-preview-11-2025:generateContent", "gemini-3-pro-preview-11-2025 | IN $3.00 OUT $18.00 | VND 9750/58500"),
            ("gemini-2.5-flash-image:generateContent", "gemini-2.5-flash-image (image) | PER $0.2250 | VND 731.25"),
            ("gemini-2.5-flash-image-preview:generateContent", "gemini-2.5-flash-image-preview (image) | PER $0.2250 | VND 731.25"),
            ("gemini-2.5-pro:generateContent", "gemini-2.5-pro | IN $1.88 OUT $15.00 | VND 6093.75/48750"),
            ("gemini-embedding-2-preview:generateContent", "gemini-embedding-2-preview (embedding) | IN $0.30 OUT $1.20 | VND 975/3900"),
            ("gemini-2.5-flash:generateContent", "gemini-2.5-flash | IN $0.45 OUT $3.75 | VND 1462.5/12197.25"),
            ("gemini-2.5-flash-nothinking:generateContent", "gemini-2.5-flash-nothinking | IN $0.45 OUT $3.75 | VND 1462.5/12197.25"),
            ("gemini-embedding-001:generateContent", "gemini-embedding-001 (embedding) | IN $0.22 OUT $0.90 | VND 731.25/2925"),
            ("gemini-2.5-flash-lite:generateContent", "gemini-2.5-flash-lite | IN $0.15 OUT $0.60 | VND 487.5/1950"),
            ("gemini-2.5-flash-lite-preview-09-2025:generateContent", "gemini-2.5-flash-lite-preview-09-2025 | IN $0.15 OUT $0.60 | VND 487.5/1950")
        ]
        self.gemini_model_map = {label: model_id for model_id, label in self.gemini_model_options}
        self.gemini_model_reverse = {model_id: label for model_id, label in self.gemini_model_options}
        self.cb_gemini['values'] = list(self.gemini_model_map.keys())

        default_gemini = "gemini-2.5-flash:generateContent"
        saved_gemini = self.main_app.config.get("gemini_model", default_gemini)
        if saved_gemini in self.gemini_model_reverse:
            self.cb_gemini.set(self.gemini_model_reverse[saved_gemini])
        else:
            self.cb_gemini.current(0)
        self.cb_gemini.pack(side="left", padx=5)

        tk.Label(row_gemini, text="(Dùng với ShopAIKey)", bg="#ffffff", font=("Arial", 9, "italic"), fg="#7f8c8d").pack(side="left", padx=10)

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
        
        # Lưu AI Provider settings
        self.main_app.config["ai_provider"] = self.ai_provider.get()
        self.main_app.config["openai_model"] = self.cb_model.get()
        selected_gemini = self.cb_gemini.get()
        self.main_app.config["gemini_model"] = self.gemini_model_map.get(selected_gemini, "gemini-2.5-flash:generateContent")
        self.main_app.config["kie_model"] = self.cb_kie.get()
        
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
            # Cập nhật Tab 2 (Groq key vẫn giữ để hiển thị)
            if hasattr(self.main_app, 'tab2') and hasattr(self.main_app.tab2, 'ent_groq'):
                self.main_app.tab2.ent_groq.delete(0, tk.END)
                self.main_app.tab2.ent_groq.insert(0, self.main_app.config.get("groq_key", ""))
            
            # Cập nhật Tab 7 (AI provider và model)
            if hasattr(self.main_app, 'tab7'):
                if hasattr(self.main_app.tab7, 'ai_provider'):
                    self.main_app.tab7.ai_provider.set(self.main_app.config.get("ai_provider", "kie"))
                if hasattr(self.main_app.tab7, 'cb_model'):
                    model = self.main_app.config.get("openai_model", "gpt-4o")
                    if model in self.main_app.tab7.cb_model['values']:
                        self.main_app.tab7.cb_model.set(model)
            
            # Cập nhật Tab 6 (Cookie)
            if hasattr(self.main_app, 'tab6') and hasattr(self.main_app.tab6, 'ent_cookie'):
                self.main_app.tab6.ent_cookie.delete(0, tk.END)
                self.main_app.tab6.ent_cookie.insert(0, self.main_app.config.get("ohfree_cookie", ""))
        except Exception as e:
            print(f"Lỗi sync config: {e}")