import os
import re
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from tab7_modules.ai_kie import KieAIHandler
from tab7_modules.scraper import ScraperHandler, HAS_YTDLP

class ScriptTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.base_dir = os.path.join(os.getcwd(), "Workspace_Data", "Kho_Kich_Ban")
        os.makedirs(self.base_dir, exist_ok=True)
        
        self.use_ytdlp = tk.BooleanVar(value=HAS_YTDLP)
        
        self.ai_handler = KieAIHandler(self)
        self.scraper_handler = ScraperHandler(self)
        
        self.setup_ui()
        self.refresh_folders()

    def setup_ui(self):
        container = tk.Frame(self.parent, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        tk.Label(container, text="🍲 TRẠM BÓC BĂNG & XÀO KỊCH BẢN TỰ ĐỘNG", font=("Arial", 14, "bold"), bg="#f4f6f9", fg="#e67e22").pack(pady=(5, 10))

        paned = ttk.PanedWindow(container, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left_frame = tk.Frame(paned, bg="#f4f6f9")
        right_frame = tk.Frame(paned, bg="#f4f6f9")
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=3) 

        # ==================== CỘT TRÁI ====================
        folder_fr = tk.LabelFrame(left_frame, text=" 1. Chiến Dịch & Sản Phẩm ", font=("Arial", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        folder_fr.pack(fill="x", pady=5)
        
        fr_f = tk.Frame(folder_fr, bg="#ffffff")
        fr_f.pack(fill="x")
        self.cb_folders = ttk.Combobox(fr_f, state="readonly", font=("Arial", 10))
        self.cb_folders.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.cb_folders.bind("<<ComboboxSelected>>", self.on_folder_selected)
        tk.Button(fr_f, text="➕ Thêm", bg="#3498db", fg="white", font=("Arial", 9, "bold"), command=self.create_folder).pack(side="right")
        # [MỚI] NÚT XÓA CHIẾN DỊCH
        tk.Button(fr_f, text="🗑️", bg="#e74c3c", fg="white", font=("Arial", 9, "bold"), command=self.delete_folder).pack(side="right", padx=(0, 2))

        tk.Label(folder_fr, text="📦 Thông Tin Sản Phẩm:", bg="#ffffff", font=("Arial", 9, "bold"), fg="#2980b9").pack(anchor="w", pady=(10, 5))
        
        prod_table_fr = tk.Frame(folder_fr)
        prod_table_fr.pack(fill="x")
        self.tree_prod = ttk.Treeview(prod_table_fr, columns=("Info",), show="headings", height=4)
        self.tree_prod.heading("Info", text="Tên & Đặc điểm chung")
        self.tree_prod.column("Info", anchor="w")
        self.tree_prod.pack(side="left", fill="x", expand=True)
        vsb_prod = ttk.Scrollbar(prod_table_fr, orient="vertical", command=self.tree_prod.yview)
        vsb_prod.pack(side="right", fill="y")
        self.tree_prod.configure(yscrollcommand=vsb_prod.set)

        btn_prod_fr = tk.Frame(folder_fr, bg="#ffffff")
        btn_prod_fr.pack(fill="x", pady=(5, 0))
        tk.Button(btn_prod_fr, text="➕", bg="#2ecc71", fg="white", font=("Arial", 8, "bold"), command=self.add_prod).pack(side="left", padx=2)
        tk.Button(btn_prod_fr, text="🗑️", bg="#e74c3c", fg="white", font=("Arial", 8, "bold"), command=self.del_prod).pack(side="left", padx=2)

        input_fr = tk.LabelFrame(left_frame, text=" 2. Setting Cào & Xào ", font=("Arial", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        input_fr.pack(fill="both", expand=True, pady=5)

        tk.Label(input_fr, text="Dán Link Video:", bg="#ffffff", font=("Arial", 9, "bold")).pack(anchor="w")
        self.txt_urls = tk.Text(input_fr, height=3, font=("Arial", 10), bg="#fdfdfd")
        self.txt_urls.pack(fill="x", pady=(0, 5))

        fr_tools = tk.Frame(input_fr, bg="#ffffff")
        fr_tools.pack(fill="x", pady=5)
        chk_ytdlp = tk.Checkbutton(fr_tools, text="🔥 yt-dlp", variable=self.use_ytdlp, font=("Arial", 9, "bold"), bg="#ffffff", fg="#c0392b")
        chk_ytdlp.pack(side="left")
        
        tk.Label(fr_tools, text=" | Luồng:", font=("Arial", 9, "bold"), bg="#ffffff").pack(side="left")
        self.spin_threads = tk.Spinbox(fr_tools, from_=1, to=10, width=5, font=("Arial", 10, "bold"))
        self.spin_threads.insert(0, "3")
        self.spin_threads.pack(side="left", padx=5)

        # =======================================================
        # [MỚI] CÔNG TẮC CHỌN GROQ / OHFREE CHO TAB 7
        # =======================================================
        fr_mode = tk.Frame(input_fr, bg="#ffffff")
        fr_mode.pack(fill="x", pady=2)
        tk.Label(fr_mode, text="Bóc Băng:", font=("Arial", 9, "bold"), bg="#ffffff", fg="#d35400").pack(side="left")
        
        # Tách biệt hoàn toàn biến lưu trữ với Tab 2 bằng key "tab7_boc_bang_mode"
        self.boc_bang_mode = tk.StringVar(value=self.main_app.config.get("tab7_boc_bang_mode", "ohfree"))
        tk.Radiobutton(fr_mode, text="OhFree (Miễn phí)", variable=self.boc_bang_mode, value="ohfree", bg="#ffffff").pack(side="left", padx=5)
        tk.Radiobutton(fr_mode, text="Groq (Tốn API)", variable=self.boc_bang_mode, value="groq", bg="#ffffff").pack(side="left")
        # =======================================================

        fr_kie = tk.Frame(input_fr, bg="#ffffff")
        fr_kie.pack(fill="x", pady=(0, 5))
        tk.Label(fr_kie, text="Kie Key:", font=("Arial", 9, "bold"), fg="#8e44ad", bg="#ffffff").pack(side="left")
        self.ent_kie = tk.Entry(fr_kie, width=25, font=("Arial", 10))
        self.ent_kie.insert(0, self.main_app.config.get("kie_key", "")) 
        self.ent_kie.pack(side="left", fill="x", expand=True, padx=5)

        tk.Label(input_fr, text="Lệnh Xào Nấu (Phong cách KOC):", bg="#ffffff", font=("Arial", 9, "bold")).pack(anchor="w")
        self.txt_setting = tk.Text(input_fr, height=7, font=("Arial", 10), bg="#f9ebea")
        
        default_prompt = """Viết kịch bản TikTok 60s từ các Key, Thông tin sản phẩm và Kịch bản gốc được cung cấp.

Yêu cầu BẮT BUỘC về phong cách (RẤT QUAN TRỌNG):
- Role: Một nam Reviewer đồ gia dụng, tư vấn chân thành, uy tín và dứt khoát.
- Ngôn từ: Có nhịp điệu tự nhiên, câu văn mượt mà, dễ lồng tiếng.
- TỪ VỰNG CẤM DÙNG: Tuyệt đối KHÔNG có các từ đuôi: "nè", "nha", "nhé", "trời ơi", "ạ", "nhỉ", "nhen".
- Các từ nên dùng: "Mình nói thật là", "Thực tế", "Thêm nữa", "Thế nên", "Ngoài ra", "Đúng là quá lời".

Cấu trúc kịch bản:
1. Hook: Đi thẳng vào lời khuyên hoặc so sánh (Nếu có Mệnh lệnh tối cao về Hook, BẮT BUỘC dùng ý đó làm câu mở đầu).
2. Thân bài: Lập luận mạch lạc. Sử dụng các cặp so sánh (Bản mới vs Bản cũ) để làm nổi bật thông số kỹ thuật. Mô tả trải nghiệm thực tế rõ ràng, logic (VD: Cắm điện, bật công tắc, di chuyển, kết quả...).
3. Chốt sale: Điều hướng dứt khoát, uy tín (VD: "Để xem giá và chọn phân loại, mọi người bấm vào giỏ hàng góc trái video để tham khảo rồi đặt mua về trải nghiệm").

Output:
- Viết thành 1 ĐOẠN VĂN HOÀN CHỈNH DUY NHẤT.
- TUYỆT ĐỐI không đánh số, không gạch đầu dòng, không xuống dòng."""
        self.txt_setting.insert("1.0", default_prompt)
        self.txt_setting.pack(fill="x")

        self.btn_run = tk.Button(left_frame, text="🚀 1. TẢI VIDEO & BÓC BĂNG", bg="#27ae60", fg="white", font=("Arial", 11, "bold"), pady=8, command=self.start_workflow)
        self.btn_run.pack(fill="x", pady=10)

        log_fr = tk.LabelFrame(left_frame, text=" Nhật Ký ", font=("Arial", 9, "bold"), bg="#ffffff")
        log_fr.pack(fill="both", expand=True)
        self.txt_log = tk.Text(log_fr, bg="#1e272e", fg="#2ecc71", font=("Consolas", 9), state="disabled", height=4)
        self.txt_log.pack(fill="both", expand=True)

        # ==================== CỘT PHẢI ====================
        list_fr = tk.LabelFrame(right_frame, text=" Danh Sách Gốc ", font=("Arial", 10, "bold"), bg="#ffffff", padx=5, pady=5)
        list_fr.pack(fill="x", pady=5, padx=(10, 0))
        
        # [MỚI] KHUNG NÚT CHO DANH SÁCH FILE
        fr_list_tools = tk.Frame(list_fr, bg="#ffffff")
        fr_list_tools.pack(side="bottom", fill="x", pady=(2, 0))
        tk.Button(fr_list_tools, text="🗑️ Xóa Kịch Bản Này", bg="#e74c3c", fg="white", font=("Arial", 8, "bold"), command=self.delete_file).pack(side="right")

        self.listbox_files = tk.Listbox(list_fr, height=4, font=("Arial", 10), selectbackground="#3498db")
        # ... (các đoạn code cuộn listbox giữ nguyên)
        self.listbox_files.pack(fill="x", side="left", expand=True)
        self.listbox_files.bind("<<ListboxSelect>>", self.load_file_content)
        scrollbar = ttk.Scrollbar(list_fr, orient="vertical", command=self.listbox_files.yview)
        scrollbar.pack(side="right", fill="y")
        self.listbox_files.config(yscrollcommand=scrollbar.set)

        text_paned = ttk.PanedWindow(right_frame, orient=tk.HORIZONTAL)
        text_paned.pack(fill="both", expand=True, padx=(10, 0), pady=5)

        orig_fr = tk.LabelFrame(text_paned, text=" 📝 Kịch Bản Gốc ", font=("Arial", 10, "bold"), bg="#ffffff", padx=5, pady=5)
        self.txt_original = tk.Text(orig_fr, font=("Arial", 11), wrap="word", bg="#f4f6f9")
        self.txt_original.pack(fill="both", expand=True)
        text_paned.add(orig_fr, weight=2)

        keys_fr = tk.LabelFrame(text_paned, text=" 🔑 Bảng Key (Chọn để làm Hook) ", font=("Arial", 10, "bold"), bg="#ffffff", padx=5, pady=5)
        self.tree_keys = ttk.Treeview(keys_fr, columns=("Key",), show="headings")
        self.tree_keys.heading("Key", text="📌 Danh sách Ý chính")
        self.tree_keys.column("Key", width=250, anchor="w")
        self.tree_keys.pack(side="top", fill="both", expand=True)
        
        vsb_keys = ttk.Scrollbar(keys_fr, orient="vertical", command=self.tree_keys.yview)
        vsb_keys.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
        self.tree_keys.configure(yscrollcommand=vsb_keys.set)
        
        btn_keys_fr = tk.Frame(keys_fr, bg="#ffffff")
        btn_keys_fr.pack(fill="x", pady=(5, 0))
        tk.Button(btn_keys_fr, text="➕", bg="#2ecc71", fg="white", font=("Arial", 8, "bold"), command=self.add_key).pack(side="left", padx=2)
        tk.Button(btn_keys_fr, text="🗑️", bg="#e74c3c", fg="white", font=("Arial", 8, "bold"), command=self.del_key).pack(side="left", padx=2)
        # Bỏ nút lên xuống đi cho gọn vì đã có cơ chế Click chọn làm Hook
        text_paned.add(keys_fr, weight=2)

        spun_fr = tk.LabelFrame(text_paned, text=" 🍲 Đã Xào ", font=("Arial", 10, "bold"), bg="#ffffff", padx=5, pady=5)
        self.txt_spun = tk.Text(spun_fr, font=("Arial", 11), wrap="word", bg="#fdfdfd")
        self.txt_spun.pack(fill="both", expand=True)
        text_paned.add(spun_fr, weight=3)

        btn_action_fr = tk.Frame(right_frame, bg="#f4f6f9")
        btn_action_fr.pack(fill="x", pady=(5, 0), padx=(10, 0))
        tk.Button(btn_action_fr, text="🔑 2. AI BÓC THÔNG TIN SP & 10 KEY", bg="#2980b9", fg="white", font=("Arial", 10, "bold"), pady=5, command=self.extract_keys_ai).pack(side="left", padx=(0, 10))
        tk.Button(btn_action_fr, text="✨ 3. XÀO KỊCH BẢN (DÙNG KEY ĐÃ CHỌN LÀM HOOK)", bg="#8e44ad", fg="white", font=("Arial", 10, "bold"), pady=5, command=self.spin_script_ai).pack(side="left")
        tk.Button(btn_action_fr, text="💾 Lưu KB Này", bg="#e67e22", fg="white", font=("Arial", 10, "bold"), pady=5, command=self.save_spun_text_only).pack(side="right")

    # --- CÁC HÀM XỬ LÝ BẢNG ---
    def add_prod(self):
        val = simpledialog.askstring("Thêm", "Nhập thông tin sản phẩm:")
        if val and val.strip():
            self.tree_prod.insert("", tk.END, values=(val.strip(),))
            self.save_global_data()

    def del_prod(self):
        for item in self.tree_prod.selection(): self.tree_prod.delete(item)
        self.save_global_data()

    def add_key(self):
        val = simpledialog.askstring("Thêm", "Nhập Key mới:")
        if val and val.strip():
            self.tree_keys.insert("", tk.END, values=(val.strip(),))
            self.save_global_data()

    def del_key(self):
        for item in self.tree_keys.selection(): self.tree_keys.delete(item)
        self.save_global_data()

    # --- QUẢN LÝ DỮ LIỆU ---
    def refresh_folders(self):
        folders = [d for d in os.listdir(self.base_dir) if os.path.isdir(os.path.join(self.base_dir, d))]
        self.cb_folders['values'] = folders
        if folders:
            self.cb_folders.current(0)
            self.on_folder_selected(None)

    def create_folder(self):
        name = simpledialog.askstring("Thêm Thư Mục", "Nhập tên thư mục chiến dịch:")
        if name:
            clean = "".join(c for c in name if c.isalnum() or c in (' ', '_')).replace(" ", "_")
            os.makedirs(os.path.join(self.base_dir, clean), exist_ok=True)
            self.refresh_folders()
            self.cb_folders.set(clean)
            self.on_folder_selected(None)
    def delete_folder(self):
        """ Xóa vĩnh viễn cả 1 chiến dịch """
        folder_name = self.cb_folders.get()
        if not folder_name: return
        
        target_dir = os.path.join(self.base_dir, folder_name)
        if not os.path.exists(target_dir): return
        
        # Cảnh báo 2 lớp
        msg = f"CẢNH BÁO: Bác có chắc muốn xóa VĨNH VIỄN chiến dịch '{folder_name}' không?\n\nToàn bộ kịch bản gốc và kịch bản đã xào trong này sẽ bị xóa sạch!"
        if messagebox.askyesno("Xác nhận Xóa", msg, icon='warning'):
            try:
                import shutil
                shutil.rmtree(target_dir) # Quét sạch thư mục
                self.add_log(f"🗑️ Đã xóa chiến dịch: {folder_name}")
                
                # Load lại danh sách Combobox
                self.refresh_folders()
                
                # Xóa chữ trên màn hình
                self.txt_original.delete("1.0", tk.END)
                self.txt_spun.delete("1.0", tk.END)
                self.tree_keys.delete(*self.tree_keys.get_children())
                self.tree_prod.delete(*self.tree_prod.get_children())
                
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể xóa thư mục: {e}")


    def on_folder_selected(self, event):
        self.txt_original.delete("1.0", tk.END)
        self.txt_spun.delete("1.0", tk.END)
        self.safe_update_listbox()

    def safe_update_listbox(self):
        folder_name = self.cb_folders.get()
        if not folder_name: return
        target_dir = os.path.join(self.base_dir, folder_name)
        if not os.path.exists(target_dir): return
        
        sel = self.listbox_files.curselection()
        selected_file = self.listbox_files.get(sel[0]) if sel else None
        
        self.listbox_files.delete(0, tk.END)
        files = sorted([f for f in os.listdir(target_dir) if f.startswith("KB_") and f.endswith(".txt")], 
                       key=lambda x: os.path.getmtime(os.path.join(target_dir, x)), reverse=True)
        for i, f in enumerate(files):
            self.listbox_files.insert(tk.END, f)
            if f == selected_file: self.listbox_files.selection_set(i)
                
        self.tree_keys.delete(*self.tree_keys.get_children())
        path_keys = os.path.join(target_dir, "global_keys.txt")
        if os.path.exists(path_keys):
            with open(path_keys, 'r', encoding='utf-8') as f:
                for line in f.read().splitlines():
                    if line.strip(): self.tree_keys.insert("", tk.END, values=(line.strip(),))
                    
        self.tree_prod.delete(*self.tree_prod.get_children())
        path_prod = os.path.join(target_dir, "product_info.txt")
        if os.path.exists(path_prod):
            with open(path_prod, 'r', encoding='utf-8') as f:
                for line in f.read().splitlines():
                    if line.strip(): self.tree_prod.insert("", tk.END, values=(line.strip(),))

    def load_file_content(self, event):
        sel = self.listbox_files.curselection()
        if not sel: return
        filename = self.listbox_files.get(sel[0])
        folder_name = self.cb_folders.get()
        base_name = filename.replace("KB_", "").replace(".txt", "")
        
        path_orig = os.path.join(self.base_dir, folder_name, filename)
        path_spun = os.path.join(self.base_dir, folder_name, f"spun_{base_name}.txt")
        
        self.txt_original.delete("1.0", tk.END)
        self.txt_spun.delete("1.0", tk.END)
        
        try:
            with open(path_orig, 'r', encoding='utf-8') as f: self.txt_original.insert("1.0", f.read())
            if os.path.exists(path_spun):
                with open(path_spun, 'r', encoding='utf-8') as f: self.txt_spun.insert("1.0", f.read())
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file: {e}")

    def delete_file(self):
        """ Xóa 1 kịch bản đang chọn """
        sel = self.listbox_files.curselection()
        if not sel: 
            return messagebox.showwarning("Chú ý", "Bác chưa chọn kịch bản nào để xóa!")
            
        filename = self.listbox_files.get(sel[0])
        folder_name = self.cb_folders.get()
        
        if messagebox.askyesno("Xác nhận", f"Xóa kịch bản '{filename}' ?"):
            path_orig = os.path.join(self.base_dir, folder_name, filename)
            
            # Tính toán tên file "Đã Xào" để xóa chung luôn cho sạch rác
            base_name = filename.replace("KB_", "").replace(".txt", "")
            path_spun = os.path.join(self.base_dir, folder_name, f"spun_{base_name}.txt")
            
            try:
                if os.path.exists(path_orig): os.remove(path_orig)
                if os.path.exists(path_spun): os.remove(path_spun)
                
                self.add_log(f"🗑️ Đã xóa kịch bản: {filename}")
                self.safe_update_listbox() # Tự load lại danh sách
                self.txt_original.delete("1.0", tk.END)
                self.txt_spun.delete("1.0", tk.END)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không xóa được: {e}")

    def save_global_data(self):
        folder_name = self.cb_folders.get()
        if not folder_name: return
        target_dir = os.path.join(self.base_dir, folder_name)
        
        all_keys = [self.tree_keys.item(c)["values"][0] for c in self.tree_keys.get_children()]
        with open(os.path.join(target_dir, "global_keys.txt"), 'w', encoding='utf-8') as f: f.write("\n".join(all_keys))
            
        all_prods = [self.tree_prod.item(c)["values"][0] for c in self.tree_prod.get_children()]
        with open(os.path.join(target_dir, "product_info.txt"), 'w', encoding='utf-8') as f: f.write("\n".join(all_prods))

    def save_spun_text_only(self):
        sel = self.listbox_files.curselection()
        if sel:
            filename = self.listbox_files.get(sel[0])
            base_name = filename.replace("KB_", "").replace(".txt", "")
            path_spun = os.path.join(self.base_dir, self.cb_folders.get(), f"spun_{base_name}.txt")
            with open(path_spun, 'w', encoding='utf-8') as f: f.write(self.txt_spun.get("1.0", tk.END).strip())
            messagebox.showinfo("Thành công", "Đã lưu Kịch Bản Xào!")

    def add_log(self, msg):
        self.main_app.root.after(0, self._insert_log, msg)

    def _insert_log(self, msg):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    # --- CHẠY CÀO VIDEO ---
    def start_workflow(self):
        raw_urls = self.txt_urls.get("1.0", tk.END).splitlines()
        urls = [u.strip() for u in raw_urls if "tiktok.com" in u.strip()]
        folder_name = self.cb_folders.get()
        cookie = self.main_app.config.get("ohfree_cookie", "")

        if not urls: return messagebox.showerror("Lỗi", "Chưa nhập link!")
        if not folder_name: return messagebox.showerror("Lỗi", "Chưa chọn thư mục!")
        if not cookie: return messagebox.showerror("Lỗi", "Chưa có Cookie OhFree (Tab 6)!")

        try: threads = int(self.spin_threads.get())
        except: threads = 3

        # [THÊM DÒNG NÀY]: Lưu lại tùy chọn vào Config
        self.main_app.config["tab7_boc_bang_mode"] = self.boc_bang_mode.get()
        self.main_app.save_config()

        self.save_global_data()
        self.btn_run.config(state="disabled", text=f"⏳ ĐANG CHẠY {threads} LUỒNG...", bg="#7f8c8d")
        
        threading.Thread(target=self._run_scraper, args=(urls, os.path.join(self.base_dir, folder_name), cookie, threads), daemon=True).start()

    def _run_scraper(self, urls, target_dir, cookie, max_workers):
        self.add_log(f"🚀 BẮT ĐẦU: Bóc {len(urls)} kịch bản với {max_workers} luồng!")
        success_count = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {executor.submit(self.scraper_handler.process_single_url, url, index, target_dir, cookie): url for index, url in enumerate(urls)}
            for future in as_completed(future_to_url):
                try:
                    if future.result(): success_count += 1
                except Exception as e:
                    self.add_log(f"❌ Lỗi văng luồng: {e}")
        self.add_log(f"🎉 HOÀN TẤT CHIẾN DỊCH! Thành công {success_count}/{len(urls)}.")
        self.main_app.root.after(0, lambda: self.btn_run.config(state="normal", text="🚀 1. TẢI VIDEO & BÓC BĂNG", bg="#27ae60"))

    # --- CHẠY GỌI AI ---
    def extract_keys_ai(self):
        orig_text = self.txt_original.get("1.0", tk.END).strip()
        kie_key = self.ent_kie.get().strip()
        
        if not orig_text: return messagebox.showerror("Lỗi", "Chưa có kịch bản gốc!")
        if not kie_key: return messagebox.showerror("Lỗi", "Chưa nhập Kie Key!")
            
        self.main_app.config["kie_key"] = kie_key
        self.main_app.save_config()
        self.add_log("⏳ Đang bắn luồng cho AI bóc Sản phẩm và 10 Key...")
        self.ai_handler.extract_info_and_keys(orig_text, kie_key)

    def spin_script_ai(self):
        orig_text = self.txt_original.get("1.0", tk.END).strip()
        system_prompt = self.txt_setting.get("1.0", tk.END).strip()
        kie_key = self.ent_kie.get().strip()
        
        all_keys = [self.tree_keys.item(c)["values"][0] for c in self.tree_keys.get_children()]
        all_prods = [self.tree_prod.item(c)["values"][0] for c in self.tree_prod.get_children()]
        
        if not orig_text: return messagebox.showerror("Lỗi", "Chưa có kịch bản gốc!")
        if not kie_key: return messagebox.showerror("Lỗi", "Chưa nhập Kie Key!")
        
        # BẮT SỰ KIỆN: Xem người dùng đang Click chọn ý nào trong 2 Bảng
        selected_hook = ""
        sel_prod = self.tree_prod.selection()
        sel_key = self.tree_keys.selection()
        
        if sel_key: # Ưu tiên lấy ở Bảng Key
            selected_hook = self.tree_keys.item(sel_key[0])["values"][0]
            self.add_log(f"🎯 Đã khóa mục tiêu Hook: {selected_hook[:30]}...")
        elif sel_prod: # Nếu không thì lấy ở Bảng Sản phẩm
            selected_hook = self.tree_prod.item(sel_prod[0])["values"][0]
            self.add_log(f"🎯 Đã khóa mục tiêu Hook: {selected_hook[:30]}...")
        else:
            self.add_log("⚠️ Chạy tự do: Không chọn Key nào làm Hook.")

        self.txt_spun.delete("1.0", tk.END)
        self.txt_spun.insert("1.0", "⏳ Đang xào kịch bản...")
        
        keys_text = "\n".join([f"- {k}" for k in all_keys])
        prod_text = "\n".join([f"- {p}" for p in all_prods])
        
        # Truyền cái selected_hook vào cho đệ tử AI
        self.ai_handler.spin_script_ai(orig_text, system_prompt, prod_text, keys_text, selected_hook, kie_key)

    def _process_ai_result(self, text, task_type):
        import re
        if task_type in ["prod_info", "keys"]:
            target_tree = self.tree_prod if task_type == "prod_info" else self.tree_keys
            lines = text.split('\n')
            for line in lines:
                clean_line = re.sub(r'^[\-\*\d\.\s]+', '', line).strip()
                garbage_words = ["dưới đây là", "thông tin sản phẩm", "key content", "ý chính"]
                if clean_line and not any(word in clean_line.lower() for word in garbage_words):
                    target_tree.insert("", tk.END, values=(clean_line,))
            
            self.save_global_data()
            msg = "Thông Tin SP" if task_type == "prod_info" else "10 Key"
            self.add_log(f"✅ Đã lọc xong {msg} vào Bảng!")
            
        elif task_type == "spun":
            self.txt_spun.delete("1.0", tk.END)
            self.txt_spun.insert("1.0", text)
            self.save_spun_text_only()
            self.add_log("✅ Đã xào xong Kịch Bản!")