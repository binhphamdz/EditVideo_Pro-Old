import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import database
from tab2_modules.ai_services import _call_ai_director


class ScriptWriterTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app

        self.project_map = []
        self.style_map = []
        self.script_map = []

        self.setup_ui()
        self.refresh_projects()
        self.refresh_styles()

    def setup_ui(self):
        container = tk.Frame(self.parent, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        header = tk.Frame(container, bg="#f4f6f9")
        header.pack(fill="x", pady=(0, 8))
        tk.Label(header, text="📝 VIẾT KỊCH BẢN (THEO PROJECT)", font=("Arial", 14, "bold"), bg="#f4f6f9", fg="#2c3e50").pack(side="left")

        top_row = tk.Frame(container, bg="#f4f6f9")
        top_row.pack(fill="x", pady=(0, 8))
        tk.Label(top_row, text="Project:", bg="#f4f6f9", font=("Arial", 10, "bold")).pack(side="left")
        self.cb_projects = ttk.Combobox(top_row, state="readonly", width=32, font=("Arial", 10))
        self.cb_projects.pack(side="left", padx=6)
        self.cb_projects.bind("<<ComboboxSelected>>", self.on_project_selected)
        tk.Button(top_row, text="🔄", bg="#95a5a6", fg="white", font=("Arial", 9, "bold"), command=self.refresh_projects).pack(side="left", padx=(0, 12))

        tk.Label(top_row, text="Phong cách:", bg="#f4f6f9", font=("Arial", 10, "bold")).pack(side="left")
        self.cb_styles = ttk.Combobox(top_row, state="readonly", width=26, font=("Arial", 10))
        self.cb_styles.pack(side="left", padx=6)
        self.cb_styles.bind("<<ComboboxSelected>>", self.on_style_selected)
        tk.Button(top_row, text="📚 Học từ SRT", bg="#8e44ad", fg="white", font=("Arial", 9, "bold"), command=self.learn_style_from_srt).pack(side="left", padx=(0, 8))
        tk.Button(top_row, text="🔄", bg="#95a5a6", fg="white", font=("Arial", 9, "bold"), command=self.refresh_styles).pack(side="left")

        paned = ttk.PanedWindow(container, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left = tk.Frame(paned, bg="#f4f6f9")
        right = tk.Frame(paned, bg="#f4f6f9")
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        scripts_fr = tk.LabelFrame(left, text=" Kịch bản đã lưu ", bg="#ffffff", font=("Arial", 10, "bold"), padx=8, pady=8)
        scripts_fr.pack(fill="both", expand=True, padx=(0, 8))

        self.list_scripts = tk.Listbox(scripts_fr, font=("Arial", 10), height=20)
        self.list_scripts.pack(side="left", fill="both", expand=True)
        self.list_scripts.bind("<<ListboxSelect>>", self.on_script_selected)
        scb = ttk.Scrollbar(scripts_fr, orient="vertical", command=self.list_scripts.yview)
        scb.pack(side="right", fill="y")
        self.list_scripts.config(yscrollcommand=scb.set)

        btn_script_row = tk.Frame(left, bg="#f4f6f9")
        btn_script_row.pack(fill="x", pady=(6, 0), padx=(0, 8))
        tk.Button(btn_script_row, text="🗑️ Xóa", bg="#e74c3c", fg="white", font=("Arial", 9, "bold"), command=self.delete_script).pack(side="left")
        tk.Button(btn_script_row, text="💾 Lưu", bg="#e67e22", fg="white", font=("Arial", 9, "bold"), command=self.save_script_manual).pack(side="left", padx=6)

        info_fr = tk.LabelFrame(right, text=" Thông tin sản phẩm ", bg="#ffffff", font=("Arial", 10, "bold"), padx=8, pady=8)
        info_fr.pack(fill="x", pady=(0, 8))
        self.lbl_product = tk.Label(info_fr, text="Chưa chọn project.", bg="#ffffff", fg="#2980b9", font=("Arial", 10, "bold"))
        self.lbl_product.pack(anchor="w")
        self.txt_context = tk.Text(info_fr, height=4, font=("Arial", 10), wrap="word", bg="#f7f9fb")
        self.txt_context.pack(fill="x", pady=(6, 0))
        self.txt_context.config(state="disabled")

        mid = ttk.PanedWindow(right, orient=tk.HORIZONTAL)
        mid.pack(fill="both", expand=True)

        keys_fr = tk.LabelFrame(mid, text=" 🔑 Key bán hàng ", bg="#ffffff", font=("Arial", 10, "bold"), padx=8, pady=8)
        self.txt_keys = tk.Text(keys_fr, font=("Arial", 10), wrap="word", bg="#fdfdfd")
        self.txt_keys.pack(fill="both", expand=True)
        mid.add(keys_fr, weight=1)

        script_fr = tk.LabelFrame(mid, text=" ✍️ Kịch bản ", bg="#ffffff", font=("Arial", 10, "bold"), padx=8, pady=8)
        self.txt_script = tk.Text(script_fr, font=("Arial", 11), wrap="word", bg="#ffffff")
        self.txt_script.pack(fill="both", expand=True)
        mid.add(script_fr, weight=2)

        style_fr = tk.LabelFrame(right, text=" Style prompt (đã học) ", bg="#ffffff", font=("Arial", 10, "bold"), padx=8, pady=8)
        style_fr.pack(fill="x", pady=(8, 8))
        self.txt_style = tk.Text(style_fr, height=4, font=("Arial", 10), wrap="word", bg="#f7f9fb")
        self.txt_style.pack(fill="x")
        self.txt_style.config(state="disabled")

        action_row = tk.Frame(right, bg="#f4f6f9")
        action_row.pack(fill="x")
        tk.Button(action_row, text="🔍 Lấy Key", bg="#2980b9", fg="white", font=("Arial", 10, "bold"), command=self.generate_keys).pack(side="left")
        tk.Button(action_row, text="✨ Viết kịch bản", bg="#27ae60", fg="white", font=("Arial", 10, "bold"), command=self.generate_script).pack(side="left", padx=8)

        tk.Label(action_row, text="Độ dài (giây):", bg="#f4f6f9", font=("Arial", 9, "bold")).pack(side="left", padx=(10, 4))
        self.spin_duration = tk.Spinbox(action_row, from_=15, to=120, width=6, font=("Arial", 10))
        self.spin_duration.delete(0, tk.END)
        self.spin_duration.insert(0, "60")
        self.spin_duration.pack(side="left")

        log_fr = tk.LabelFrame(right, text=" Nhật ký ", bg="#ffffff", font=("Arial", 9, "bold"))
        log_fr.pack(fill="both", expand=True, pady=(8, 0))
        self.txt_log = tk.Text(log_fr, bg="#1e272e", fg="#2ecc71", font=("Consolas", 9), state="disabled", height=5)
        self.txt_log.pack(fill="both", expand=True)

    def refresh_projects(self):
        self.project_map = []
        projects = self.main_app.projects or {}
        for pid, pdata in projects.items():
            name = str((pdata or {}).get("name", "")).strip()
            if name:
                self.project_map.append((pid, name))

        names = [name for _, name in self.project_map]
        self.cb_projects["values"] = names

        current_pid = getattr(self.main_app.tab1, "current_project_id", None)
        if current_pid:
            for idx, (pid, _) in enumerate(self.project_map):
                if pid == current_pid:
                    self.cb_projects.current(idx)
                    self.on_project_selected()
                    return

        if names:
            self.cb_projects.current(0)
            self.on_project_selected()

    def refresh_styles(self):
        profile = self.main_app.get_active_profile_name()
        self.style_map = []
        rows = database.list_script_styles(profile)
        for row in rows:
            self.style_map.append((row["id"], row["name"], row["prompt"]))
        self.cb_styles["values"] = [name for _, name, _ in self.style_map]
        if self.style_map:
            self.cb_styles.current(0)
            self.on_style_selected()
        else:
            self.txt_style.config(state="normal")
            self.txt_style.delete("1.0", tk.END)
            self.txt_style.config(state="disabled")

    def on_project_selected(self, event=None):
        proj_name = self.get_selected_project_name()
        if not proj_name:
            return

        p_data = self.main_app.get_project_data(self.get_selected_project_id())
        self.lbl_product.config(text=f"{proj_name}")
        context = p_data.get("product_context", "")
        if p_data.get("product_name"):
            context = f"{p_data.get('product_name')}\n{context}".strip()

        self.txt_context.config(state="normal")
        self.txt_context.delete("1.0", tk.END)
        self.txt_context.insert("1.0", context)
        self.txt_context.config(state="disabled")

        self.load_scripts_list()

    def on_style_selected(self, event=None):
        style = self.get_selected_style()
        self.txt_style.config(state="normal")
        self.txt_style.delete("1.0", tk.END)
        if style:
            self.txt_style.insert("1.0", style[2])
        self.txt_style.config(state="disabled")

    def load_scripts_list(self):
        self.script_map = []
        self.list_scripts.delete(0, tk.END)
        proj_name = self.get_selected_project_name()
        if not proj_name:
            return
        rows = database.list_project_scripts(proj_name)
        for row in rows:
            title = row["title"] or "(Không tiêu đề)"
            style = row["style_name"] or ""
            created_at = row["created_at"] if "created_at" in row.keys() else ""
            label = f"{str(created_at)[:16]} | {title} | {style}" if created_at else f"{title} | {style}"
            self.script_map.append((row["id"], label))
            self.list_scripts.insert(tk.END, label)

    def on_script_selected(self, event=None):
        idxs = self.list_scripts.curselection()
        if not idxs:
            return
        script_id = self.script_map[idxs[0]][0]
        row = database.get_project_script(script_id)
        if not row:
            return

        self.txt_script.delete("1.0", tk.END)
        self.txt_script.insert("1.0", row["content"] or "")

        self.txt_keys.delete("1.0", tk.END)
        try:
            keys = json.loads(row["keys_json"] or "[]")
            if isinstance(keys, list):
                self.txt_keys.insert("1.0", "\n".join(keys))
        except Exception:
            pass

    def delete_script(self):
        idxs = self.list_scripts.curselection()
        if not idxs:
            return
        script_id = self.script_map[idxs[0]][0]
        if not messagebox.askyesno("Xóa", "Xóa kịch bản này?"):
            return
        database.delete_project_script(script_id)
        self.load_scripts_list()

    def save_script_manual(self):
        proj_name = self.get_selected_project_name()
        if not proj_name:
            return
        content = self.txt_script.get("1.0", tk.END).strip()
        if not content:
            return messagebox.showwarning("Thiếu", "Chưa có kịch bản để lưu.")
        keys = self._read_keys_from_ui()
        style = self.get_selected_style()
        style_id = style[0] if style else None
        title = self._build_title_from_script(content)
        database.add_project_script(proj_name, title, content, keys=keys, style_id=style_id)
        self.load_scripts_list()

    def learn_style_from_srt(self):
        files = filedialog.askopenfilenames(title="Chọn file SRT", filetypes=[("SRT", "*.srt"), ("All", "*.*")])
        if not files:
            return
        threading.Thread(target=self._learn_style_worker, args=(files,), daemon=True).start()

    def _learn_style_worker(self, files):
        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    srt_text = f.read().strip()
            except Exception:
                continue
            if not srt_text:
                continue

            prompt = self._build_style_prompt(srt_text)
            try:
                result = self._call_ai_json(prompt, task="style")
            except Exception as exc:
                self.add_log(f"❌ Lỗi học phong cách: {exc}")
                continue

            style_name = str(result.get("style_name") or "").strip() or os.path.splitext(os.path.basename(path))[0]
            style_prompt = str(result.get("style_prompt") or "").strip()
            notes = str(result.get("notes") or "").strip()
            if not style_prompt:
                self.add_log(f"⚠️ Bỏ qua {style_name}: phong cách rỗng.")
                continue

            profile = self.main_app.get_active_profile_name()
            style_id = database.upsert_script_style(profile, style_name, style_prompt, notes)
            if style_id:
                database.add_script_style_sample(style_id, os.path.basename(path), srt_text)
                self.add_log(f"✅ Đã lưu phong cách: {style_name}")

        self.main_app.root.after(0, self.refresh_styles)

    def generate_keys(self):
        proj_name = self.get_selected_project_name()
        if not proj_name:
            return

        product_info = self._get_product_context_text()
        if not product_info:
            return messagebox.showwarning("Thiếu", "Project chưa có bối cảnh sản phẩm.")

        prompt = self._build_keys_prompt(product_info)
        threading.Thread(target=self._keys_worker, args=(prompt,), daemon=True).start()

    def _keys_worker(self, prompt):
        try:
            result = self._call_ai_json(prompt, task="keys")
            keys = result.get("keys", [])
            if not isinstance(keys, list):
                keys = []
            self.main_app.root.after(0, lambda: self._apply_keys(keys))
            self.add_log("✅ Đã lấy key bán hàng.")
        except Exception as exc:
            self.add_log(f"❌ Lỗi lấy key: {exc}")

    def _apply_keys(self, keys):
        self.txt_keys.delete("1.0", tk.END)
        self.txt_keys.insert("1.0", "\n".join([str(k).strip() for k in keys if str(k).strip()]))

    def generate_script(self):
        proj_name = self.get_selected_project_name()
        if not proj_name:
            return

        product_info = self._get_product_context_text()
        if not product_info:
            return messagebox.showwarning("Thiếu", "Project chưa có bối cảnh sản phẩm.")

        keys = self._read_keys_from_ui()
        style = self.get_selected_style()
        style_prompt = style[2] if style else ""
        duration = str(self.spin_duration.get()).strip() or "60"

        prompt = self._build_script_prompt(product_info, keys, style_prompt, duration)
        threading.Thread(target=self._script_worker, args=(prompt, keys, style), daemon=True).start()

    def _script_worker(self, prompt, keys, style):
        try:
            result = self._call_ai_json(prompt, task="script")
            script_text = str(result.get("script") or "").strip()
            if not script_text:
                raise Exception("Script rỗng")
            title = str(result.get("title") or "").strip() or self._build_title_from_script(script_text)

            proj_name = self.get_selected_project_name()
            style_id = style[0] if style else None
            database.add_project_script(proj_name, title, script_text, keys=keys, style_id=style_id)

            def _apply():
                self.txt_script.delete("1.0", tk.END)
                self.txt_script.insert("1.0", script_text)
                self.load_scripts_list()
            self.main_app.root.after(0, _apply)
            self.add_log("✅ Đã tạo kịch bản và lưu.")
        except Exception as exc:
            self.add_log(f"❌ Lỗi viết kịch bản: {exc}")

    def _get_product_context_text(self):
        return self.txt_context.get("1.0", tk.END).strip()

    def _read_keys_from_ui(self):
        raw = self.txt_keys.get("1.0", tk.END)
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _build_title_from_script(self, content):
        words = [w for w in content.replace("\n", " ").split() if w.strip()]
        return " ".join(words[:6])

    def _build_keys_prompt(self, product_info):
        return (
            "Bạn là nhân viên content bán hàng chuyên nghiệp. "
            "Hãy đọc thông tin sản phẩm và tạo ra các key bán hàng (8-12 ý). "
            "Trả về JSON với format: {\"keys\": [\"...\"]}.\n\n"
            f"THÔNG TIN SẢN PHẨM:\n{product_info}\n"
        )

    def _build_script_prompt(self, product_info, keys, style_prompt, duration):
        keys_text = "\n".join([f"- {k}" for k in keys]) if keys else ""
        base_role = (
            "Bạn là một nhân viên content chuyên nghiệp chuyên bán hàng trên TikTok. "
            "Nội dung phải thuyết phục, có nhịp điệu tự nhiên, dễ lồng tiếng, "
            "tập trung lợi ích và bằng chứng cụ thể."
        )
        style_block = f"\n\nPHONG CACH CAN AP DUNG:\n{style_prompt}" if style_prompt else ""
        return (
            f"{base_role}\n"
            f"Viet kich ban ban hang do dai ~{duration}s. "
            "Tra ve JSON format: {\"title\": \"...\", \"script\": \"...\"}.\n\n"
            f"THONG TIN SAN PHAM:\n{product_info}\n\n"
            f"KEY BAN HANG:\n{keys_text}\n"
            f"{style_block}"
        )

    def _build_style_prompt(self, srt_text):
        return (
            "Doc SRT va rut ra phong cach kich ban. "
            "Tra ve JSON format: {\"style_name\": \"...\", \"style_prompt\": \"...\", \"notes\": \"...\"}.\n\n"
            "style_prompt phai la huong dan ro rang de AI co the noi theo.\n\n"
            f"SRT:\n{srt_text[:6000]}"
        )

    def _call_ai_json(self, prompt, task="script"):
        provider = self.main_app.config.get("ai_provider", "kie")
        if provider == "shopaikey":
            model = self.main_app.config.get("shopaikey_model", "gemini-2.5-flash:generateContent")
        elif provider == "openai":
            model = self.main_app.config.get("openai_model", "gpt-4o-mini")
        else:
            model = self.main_app.config.get("kie_model", "gemini-3-flash")

        temperature = 0.3 if task in ("keys", "style") else 0.6
        text = _call_ai_director(prompt, self.main_app.config, provider=provider, model=model, temperature=temperature, timeout=180)
        return self._safe_json_load(text)

    def _safe_json_load(self, text):
        try:
            return json.loads(text)
        except Exception:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass

        return {}

    def get_selected_project_id(self):
        idx = self.cb_projects.current()
        if idx < 0 or idx >= len(self.project_map):
            return None
        return self.project_map[idx][0]

    def get_selected_project_name(self):
        idx = self.cb_projects.current()
        if idx < 0 or idx >= len(self.project_map):
            return ""
        return self.project_map[idx][1]

    def get_selected_style(self):
        idx = self.cb_styles.current()
        if idx < 0 or idx >= len(self.style_map):
            return None
        return self.style_map[idx]

    def add_log(self, msg):
        if not msg:
            return
        def _write():
            self.txt_log.config(state="normal")
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)
            self.txt_log.config(state="disabled")
        if hasattr(self.main_app, "root") and self.main_app.root:
            self.main_app.root.after(0, _write)
        else:
            _write()
