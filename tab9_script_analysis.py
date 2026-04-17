import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re

class ScriptAnalysisTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.sentence_vars = [] # Lưu danh sách các biến Checkbox
        self.script_path_map = {} # Lưu đường dẫn chính xác của từng file
        self.setup_ui()

    def setup_ui(self):
        self.container = tk.Frame(self.parent, bg="#f4f6f9")
        self.container.pack(fill="both", expand=True, padx=10, pady=10)

        # ================= HEADER: CHỌN SẢN PHẨM =================
        header_fr = tk.Frame(self.container, bg="#ffffff", bd=1, relief="solid", padx=10, pady=10)
        header_fr.pack(fill="x", pady=(0, 10))

        tk.Label(header_fr, text="📦 Chọn Sản Phẩm (Trong Kho Kịch Bản):", font=("Arial", 11, "bold"), bg="#ffffff", fg="#2c3e50").pack(side="left", padx=5)
        
        self.cb_projects = ttk.Combobox(header_fr, width=40, state="readonly", font=("Arial", 10))
        self.cb_projects.pack(side="left", padx=10)
        self.cb_projects.bind("<<ComboboxSelected>>", self.on_project_selected)

        tk.Button(header_fr, text="🔄 Làm Mới Danh Sách", bg="#3498db", fg="white", font=("Arial", 9, "bold"), command=self.load_projects).pack(side="left", padx=5)

        # ================= BODY: 3 CỘT TƯƠNG TÁC =================
        body_fr = tk.Frame(self.container, bg="#f4f6f9")
        body_fr.pack(fill="both", expand=True)

        # --- CỘT 1: KỊCH BẢN GỐC ---
        col1 = tk.LabelFrame(body_fr, text=" 📝 Kịch Bản Gốc (Raw) ", font=("Arial", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        col1.pack(side="left", fill="both", expand=True, padx=(0, 5))

        tk.Label(col1, text="1. Chọn file kịch bản:", font=("Arial", 9, "bold"), bg="#ffffff", fg="#2980b9").pack(anchor="w")
        self.lst_scripts = tk.Listbox(col1, height=5, font=("Arial", 10), exportselection=False)
        self.lst_scripts.pack(fill="x", pady=(0, 5))
        self.lst_scripts.bind("<<ListboxSelect>>", self.on_script_selected)

        tk.Label(col1, text="2. Nội dung kịch bản:", font=("Arial", 9, "bold"), bg="#ffffff", fg="#2980b9").pack(anchor="w")
        self.txt_raw = tk.Text(col1, font=("Arial", 10), wrap="word", bg="#fdfefe")
        self.txt_raw.pack(fill="both", expand=True, pady=5)

        tk.Button(col1, text="✂️ BĂM NHỎ KỊCH BẢN", bg="#d35400", fg="white", font=("Arial", 11, "bold"), pady=8, command=self.split_sentences).pack(fill="x", pady=(5, 0))

        # --- CỘT 2: DANH SÁCH CÂU (CHECKBOX) ---
        col2 = tk.LabelFrame(body_fr, text=" 🔍 Phân Tích & Chọn Câu ", font=("Arial", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        col2.pack(side="left", fill="both", expand=True, padx=5)

        self.canvas = tk.Canvas(col2, bg="#fdfefe", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(col2, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#fdfefe")

        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        btn_fr2 = tk.Frame(col2, bg="#ffffff")
        btn_fr2.pack(side="bottom", fill="x", pady=(10, 0))
        tk.Button(btn_fr2, text="☑ Chọn Hết", bg="#7f8c8d", fg="white", command=self.select_all).pack(side="left", expand=True, fill="x", padx=(0, 2))
        tk.Button(btn_fr2, text="☐ Bỏ Chọn", bg="#7f8c8d", fg="white", command=self.deselect_all).pack(side="left", expand=True, fill="x", padx=(2, 0))
        
        # Nút Đổi tên và Chức năng: Append vào giỏ hàng
        tk.Button(col2, text="➕ THÊM CÂU VÀO BẢN CHỐT", bg="#27ae60", fg="white", font=("Arial", 11, "bold"), pady=8, command=self.append_to_final).pack(side="bottom", fill="x", pady=(10, 5))

        # --- CỘT 3: KỊCH BẢN CHỐT ---
        col3 = tk.LabelFrame(body_fr, text=" ✨ Kịch Bản Chốt (Giỏ Hàng) ", font=("Arial", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        col3.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # Khung Tiêu đề Cột 3 + Nút Xóa trắng
        col3_header = tk.Frame(col3, bg="#ffffff")
        col3_header.pack(fill="x", pady=(0, 5))
        tk.Label(col3_header, text="Các câu chọn sẽ được CỘNG DỒN xuống dưới:", font=("Arial", 9, "italic"), bg="#ffffff", fg="#7f8c8d").pack(side="left")
        tk.Button(col3_header, text="🗑️ Xóa Trắng", bg="#e74c3c", fg="white", font=("Arial", 8, "bold"), command=self.clear_final).pack(side="right")
        
        self.txt_final = tk.Text(col3, font=("Arial", 15, "bold"), wrap="word", bg="#e8f8f5", spacing1=5)
        self.txt_final.pack(fill="both", expand=True, pady=5)

        btn_fr3 = tk.Frame(col3, bg="#ffffff")
        btn_fr3.pack(fill="x", pady=(5, 0))
        tk.Button(btn_fr3, text="📋 Copy Kịch Bản", bg="#8e44ad", fg="white", font=("Arial", 10, "bold"), pady=8, command=self.copy_final).pack(side="left", expand=True, fill="x", padx=(0, 5))
        tk.Button(btn_fr3, text="💾 Lưu File .txt", bg="#2980b9", fg="white", font=("Arial", 10, "bold"), pady=8, command=self.save_final_txt).pack(side="right", expand=True, fill="x")

        self.load_projects()

    # ================= CÁC HÀM XỬ LÝ =================

    def _on_mousewheel(self, event):
        try: self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except: pass

    def get_kho_kich_ban_dir(self):
        kho_dir = os.path.join(os.getcwd(), "Workspace_Data", "Kho_Kich_Ban")
        os.makedirs(kho_dir, exist_ok=True)
        return kho_dir

    def load_projects(self):
        self.cb_projects['values'] = []
        kho_dir = self.get_kho_kich_ban_dir()
        
        if os.path.exists(kho_dir):
            proj_names = [d for d in os.listdir(kho_dir) if os.path.isdir(os.path.join(kho_dir, d))]
            self.cb_projects['values'] = proj_names
            if proj_names:
                self.cb_projects.current(0)
                self.on_project_selected(None)

    def on_project_selected(self, event):
        # [AUTO-SAVE] Trước khi đổi Project, hốt hết các câu đang tick dở vào giỏ hàng
        self.append_to_final(silent=True)

        self.lst_scripts.delete(0, tk.END)
        self.txt_raw.delete("1.0", tk.END)
        self.script_path_map.clear()
        
        selection = self.cb_projects.get()
        if not selection: return
        
        proj_dir = os.path.join(self.get_kho_kich_ban_dir(), selection)
        
        if os.path.exists(proj_dir):
            for root_dir, dirs, files in os.walk(proj_dir):
                for f in files:
                    # [CHỈ CHỈNH SỬA Ở DÒNG NÀY] Bắt buộc đuôi .txt VÀ tên file bắt đầu bằng chữ KB
                    if f.lower().endswith(".txt") and f.upper().startswith("KB"):
                        if f not in self.script_path_map:
                            self.lst_scripts.insert(tk.END, f)
                            self.script_path_map[f] = os.path.join(root_dir, f)

    def on_script_selected(self, event):
        # [AUTO-SAVE] Trước khi đổi File Script, hốt hết các câu đang tick dở vào giỏ hàng
        self.append_to_final(silent=True)

        selected = self.lst_scripts.curselection()
        if not selected: return
        
        file_name = self.lst_scripts.get(selected[0])
        file_path = self.script_path_map.get(file_name)
            
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    content = file.read()
                self.txt_raw.delete("1.0", tk.END)
                self.txt_raw.insert("1.0", content.strip())
                # Xóa sạch bảng Checkbox cũ
                for widget in self.scroll_frame.winfo_children(): widget.destroy()
                self.sentence_vars.clear()
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không đọc được file: {e}")

    def split_sentences(self):
        # [AUTO-SAVE] Trước khi băm lại, hốt hết các câu đang tick dở
        self.append_to_final(silent=True)

        raw_text = self.txt_raw.get("1.0", tk.END).strip()
        if not raw_text:
            return messagebox.showwarning("Chú ý", "Cột kịch bản gốc đang trống rỗng bác ơi!")

        for widget in self.scroll_frame.winfo_children(): widget.destroy()
        self.sentence_vars.clear()

        # Băm câu thông minh
        sentences = re.split(r'(?<=[.!?])\s+|\n+', raw_text)
        valid_sentences = [s.strip() for s in sentences if len(s.strip()) > 3]

        if not valid_sentences:
            return messagebox.showinfo("Thông báo", "Không tìm thấy câu nào hợp lệ để cắt!")

        for i, sentence in enumerate(valid_sentences):
            var = tk.BooleanVar(value=False)
            self.sentence_vars.append((var, sentence))
            
            row_fr = tk.Frame(self.scroll_frame, bg="#fdfefe", pady=3)
            row_fr.pack(fill="x", anchor="w")
            
            chk = tk.Checkbutton(row_fr, variable=var, bg="#fdfefe", activebackground="#fdfefe")
            chk.pack(side="left", anchor="nw")
            
            lbl = tk.Label(row_fr, text=f"{sentence}", bg="#fdfefe", justify="left", wraplength=380, font=("Arial", 10))
            lbl.pack(side="left", anchor="nw")
            
            lbl.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))

    def select_all(self):
        for var, _ in self.sentence_vars: var.set(True)

    def deselect_all(self):
        for var, _ in self.sentence_vars: var.set(False)

    # ================= LOGIC GIỎ HÀNG (CỘNG DỒN) =================
    def append_to_final(self, silent=False):
        """Lấy các câu đang tick và NỐI VÀO ĐUÔI kịch bản chốt"""
        selected_texts = [text for var, text in self.sentence_vars if var.get()]
        
        if not selected_texts:
            if not silent:
                messagebox.showwarning("Chú ý", "Bác chưa tích chọn câu nào cả!")
            return

        # Nối các câu thành 1 đoạn văn, thêm dấu cách
        # Nối các câu thành từng dòng riêng biệt, thêm 1 dòng trống ở cuối cho thoáng
        added_script = "\n".join(selected_texts) + "\n\n"
        
        # INSERT (Chèn) vào cuối cùng (tk.END) thay vì Delete
        self.txt_final.insert(tk.END, added_script)
        
        # Bỏ chọn các ô đã tích để tránh nháy đúp
        self.deselect_all()
        
        if not silent:
            # Nháy màu xanh nhẹ ở Cột 3 để báo hiệu "Đã cho vào giỏ"
            self.txt_final.config(bg="#d1f2eb")
            self.parent.after(300, lambda: self.txt_final.config(bg="#e8f8f5"))

    def clear_final(self):
        if messagebox.askyesno("Xóa Trắng", "Bác có chắc muốn xóa sạch Kịch bản chốt để làm lại từ đầu không?"):
            self.txt_final.delete("1.0", tk.END)

    def copy_final(self):
        final_text = self.txt_final.get("1.0", tk.END).strip()
        if final_text:
            self.container.clipboard_clear()
            self.container.clipboard_append(final_text)
            messagebox.showinfo("Đã Copy", "Đã copy kịch bản chốt vào Khay nhớ tạm!")

    def save_final_txt(self):
        final_text = self.txt_final.get("1.0", tk.END).strip()
        if not final_text:
            return messagebox.showwarning("Trống", "Kịch bản chốt chưa có gì để lưu!")

        selection = self.cb_projects.get()
        if not selection: return
        
        proj_dir = os.path.join(self.get_kho_kich_ban_dir(), selection)
        
        file_path = filedialog.asksaveasfilename(
            initialdir=proj_dir,
            title="Lưu Kịch Bản Mới",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile="KichBan_XaoLai.txt"
        )
        
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(final_text)
                messagebox.showinfo("Thành công", "Đã lưu kịch bản thành file .txt!")
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không lưu được file: {e}")