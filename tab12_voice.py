import os
import re
import threading
import time
import tkinter as tk
import unicodedata
from tkinter import ttk, messagebox, simpledialog

import requests


class TabVoice:
    def __init__(self, master, parent_app):
        self.master = master
        self.parent_app = parent_app
        self.current_project_id = None
        self.project_map = {}

        self.voice_id_candidates = self._load_voice_id_candidates()
        self.voice_aliases = self._load_voice_aliases()
        self.default_speaker_id = "voice-02a1e0b5-bafd-497c"

        self.setup_ui()
        self.refresh_projects(initial=True)

    def setup_ui(self):
        container = tk.Frame(self.master, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        header = tk.Label(
            container,
            text="🎙️ TẠO VOICE THEO PROJECT",
            font=("Arial", 14, "bold"),
            bg="#f4f6f9",
            fg="#2c3e50",
        )
        header.pack(anchor="w", pady=(0, 8))

        paned = ttk.PanedWindow(container, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left_frame = tk.Frame(paned, bg="#f4f6f9")
        right_frame = tk.Frame(paned, bg="#f4f6f9")
        paned.add(left_frame, weight=2)
        paned.add(right_frame, weight=3)

        # ==================== LEFT: PROJECT + VOICE LIST ====================
        proj_fr = tk.LabelFrame(left_frame, text=" Project ", font=("Arial", 10, "bold"), bg="#ffffff", padx=10, pady=8)
        proj_fr.pack(fill="x", pady=5)

        proj_row = tk.Frame(proj_fr, bg="#ffffff")
        proj_row.pack(fill="x")
        tk.Label(proj_row, text="Chọn Project:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.cb_projects = ttk.Combobox(proj_row, state="readonly", font=("Arial", 10))
        self.cb_projects.pack(side="left", fill="x", expand=True, padx=6)
        self.cb_projects.bind("<<ComboboxSelected>>", self._on_project_changed)
        tk.Button(proj_row, text="↻", width=3, command=self.refresh_projects).pack(side="right")

        self.lbl_project_hint = tk.Label(proj_fr, text="Chưa chọn project", bg="#ffffff", fg="#7f8c8d", font=("Arial", 9))
        self.lbl_project_hint.pack(anchor="w", pady=(6, 0))

        list_fr = tk.LabelFrame(left_frame, text=" Danh sách Voice (theo Project) ", font=("Arial", 10, "bold"), bg="#ffffff", padx=5, pady=5)
        list_fr.pack(fill="both", expand=True, pady=5)

        self.tree_voices = ttk.Treeview(list_fr, columns=("name", "usage", "time", "action"), show="headings", height=10)
        self.tree_voices.heading("name", text="Tên Voice")
        self.tree_voices.heading("usage", text="Số lần dùng")
        self.tree_voices.heading("time", text="Cập nhật")
        self.tree_voices.heading("action", text="Chức năng")
        self.tree_voices.column("name", width=210, anchor="w")
        self.tree_voices.column("usage", width=90, anchor="center")
        self.tree_voices.column("time", width=120, anchor="center")
        self.tree_voices.column("action", width=120, anchor="center")
        self.tree_voices.pack(side="left", fill="both", expand=True)
        self.tree_voices.bind("<Button-1>", self._on_voice_action_click)
        self.tree_voices.bind("<Button-3>", self._on_voice_right_click)
        self.tree_voices.bind("<B1-Motion>", self._on_voice_drag_select)

        scroll = ttk.Scrollbar(list_fr, orient="vertical", command=self.tree_voices.yview)
        scroll.pack(side="right", fill="y")
        self.tree_voices.configure(yscrollcommand=scroll.set)

        btn_row = tk.Frame(left_frame, bg="#f4f6f9")
        btn_row.pack(fill="x", pady=(6, 0))
        tk.Button(btn_row, text="↻ Tải lại", bg="#3498db", fg="white", font=("Arial", 9, "bold"), command=self.load_voices).pack(side="left", padx=4)

        # ==================== RIGHT: CREATE VOICE ====================
        gen_fr = tk.LabelFrame(right_frame, text=" Tạo Voice ", font=("Arial", 10, "bold"), bg="#ffffff", padx=10, pady=10)
        gen_fr.pack(fill="both", expand=True, padx=(8, 0), pady=5)

        key_row = tk.Frame(gen_fr, bg="#ffffff")
        key_row.pack(fill="x")
        tk.Label(key_row, text="EverAI API Key:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.api_key_entry = ttk.Entry(key_row, width=45)
        self.api_key_entry.pack(side="left", padx=8, fill="x", expand=True)
        saved_key = str(self.parent_app.config.get("everai_key", "") or "").strip()
        if saved_key:
            self.api_key_entry.insert(0, saved_key)
        self.api_key_entry.bind("<FocusOut>", self._save_api_key)
        self.api_key_entry.bind("<KeyRelease>", self._schedule_save_api_key)

        voice_id_fr = tk.LabelFrame(gen_fr, text=" Voice ID (EverAI) ", font=("Arial", 9, "bold"), bg="#ffffff", padx=8, pady=6)
        voice_id_fr.pack(fill="x", pady=(8, 0))

        voice_id_row = tk.Frame(voice_id_fr, bg="#ffffff")
        voice_id_row.pack(fill="x")
        tk.Label(voice_id_row, text="Danh sách:", bg="#ffffff", font=("Arial", 9, "bold"), width=10, anchor="w").pack(side="left")
        self.voice_id_var = tk.StringVar()
        self.cb_voice_ids = ttk.Combobox(voice_id_row, state="readonly", width=36, textvariable=self.voice_id_var)
        self.cb_voice_ids.pack(side="left", padx=(0, 6), fill="x", expand=True)
        tk.Button(voice_id_row, text="Đặt tên", width=8, command=self._rename_voice_id).pack(side="right")

        voice_manual_row = tk.Frame(voice_id_fr, bg="#ffffff")
        voice_manual_row.pack(fill="x", pady=(6, 0))
        tk.Label(voice_manual_row, text="Nhập tay:", bg="#ffffff", font=("Arial", 9, "bold"), width=10, anchor="w").pack(side="left")
        self.voice_id_entry = ttk.Entry(voice_manual_row, width=36)
        self.voice_id_entry.pack(side="left", fill="x", expand=True)

        name_row = tk.Frame(gen_fr, bg="#ffffff")
        name_row.pack(fill="x", pady=(8, 0))
        tk.Label(name_row, text="Tên Voice:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.voice_name_entry = ttk.Entry(name_row, width=30)
        self.voice_name_entry.pack(side="left", padx=8, fill="x", expand=True)
        self.voice_name_entry.config(state="readonly")

        tk.Label(gen_fr, text="Nội dung chuyển thành giọng nói:", bg="#ffffff", font=("Arial", 9, "bold")).pack(anchor="w", pady=(10, 2))
        self.text_input = tk.Text(gen_fr, height=12, wrap="word", font=("Arial", 11), bg="#fdfdfd")
        self.text_input.pack(fill="both", expand=True)

        speed_row = tk.Frame(gen_fr, bg="#ffffff")
        speed_row.pack(fill="x", pady=(10, 0))
        tk.Label(speed_row, text="Tốc độ đọc:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.speed_slider = tk.Scale(speed_row, from_=0.5, to=2.0, resolution=0.1, orient="horizontal", length=200)
        self.speed_slider.set(1.0)
        self.speed_slider.pack(side="left", padx=8)

        pitch_row = tk.Frame(gen_fr, bg="#ffffff")
        pitch_row.pack(fill="x", pady=(6, 0))
        tk.Label(pitch_row, text="Cao độ:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.pitch_slider = tk.Scale(pitch_row, from_=0.5, to=2.0, resolution=0.1, orient="horizontal", length=200)
        self.pitch_slider.set(1.0)
        self.pitch_slider.pack(side="left", padx=8)

        bitrate_row = tk.Frame(gen_fr, bg="#ffffff")
        bitrate_row.pack(fill="x", pady=(6, 0))
        tk.Label(bitrate_row, text="Bitrate:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.bitrate_var = tk.StringVar(value="128")
        self.cb_bitrate = ttk.Combobox(bitrate_row, state="readonly", width=10, textvariable=self.bitrate_var)
        self.cb_bitrate["values"] = ["64", "96", "128", "192", "256"]
        self.cb_bitrate.pack(side="left", padx=8)

        self.btn_generate = tk.Button(
            gen_fr,
            text="🚀 TẠO VOICE & LƯU VÀO PROJECT",
            font=("Arial", 12, "bold"),
            bg="#4CAF50",
            fg="white",
            height=2,
            command=self.start_generate_thread,
        )
        self.btn_generate.pack(fill="x", pady=(12, 4))

        status_fr = tk.Frame(gen_fr, bg="#ffffff")
        status_fr.pack(fill="x", pady=(6, 0))
        self.lbl_status = tk.Label(status_fr, text="", bg="#ffffff", fg="#7f8c8d", font=("Arial", 9, "italic"))
        self.lbl_status.pack(anchor="w")

        self.lbl_request = tk.Label(status_fr, text="", bg="#ffffff", fg="#95a5a6", font=("Arial", 9))
        self.lbl_request.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(status_fr, orient="horizontal", mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", pady=(4, 0))
        self.lbl_progress = tk.Label(status_fr, text="", bg="#ffffff", fg="#7f8c8d", font=("Arial", 9))
        self.lbl_progress.pack(anchor="w")

        self._refresh_voice_id_list()

    def on_tab_activated(self):
        self.refresh_projects(sync_from_tab1=True)

    def refresh_projects(self, initial=False, sync_from_tab1=False):
        projects = self.parent_app.projects or {}
        sorted_projects = sorted(projects.items(), key=lambda x: x[1].get("created_at", 0), reverse=True)

        self.project_map = {pdata.get("name", pid): pid for pid, pdata in sorted_projects}
        project_names = list(self.project_map.keys())

        self.cb_projects["values"] = project_names
        if not project_names:
            self.current_project_id = None
            self.cb_projects.set("")
            self.lbl_project_hint.config(text="Chưa có project", fg="#c0392b")
            self.load_voices(clear_only=True)
            return

        target_pid = self.current_project_id
        if sync_from_tab1 and hasattr(self.parent_app, "tab1"):
            tab1_pid = getattr(self.parent_app.tab1, "current_project_id", None)
            if tab1_pid:
                target_pid = tab1_pid

        if target_pid and target_pid in projects:
            target_name = projects[target_pid].get("name", target_pid)
            self.cb_projects.set(target_name)
            self.set_project(target_pid, refresh_list=not initial)
        else:
            self.cb_projects.current(0)
            self._on_project_changed()

    def set_project(self, project_id, refresh_list=True):
        if not project_id or project_id not in (self.parent_app.projects or {}):
            return
        self.current_project_id = project_id
        proj_name = self.parent_app.projects[project_id].get("name", project_id)
        self.lbl_project_hint.config(text=f"Đang chọn: {proj_name}", fg="#2c3e50")
        if refresh_list:
            self.load_voices()
        self._set_voice_name_display()

    def _on_project_changed(self, event=None):
        name = self.cb_projects.get()
        pid = self.project_map.get(name)
        if pid:
            self.set_project(pid)

    def _clean_project_name(self, name):
        """Giống Tab 1: bỏ dấu, viết liền, giữ số thứ tự."""
        text = str(name or "").strip()
        if not text:
            return "project"
        text = text.replace("Đ", "D").replace("đ", "d")
        normalized = unicodedata.normalize("NFD", text)
        no_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        clean_name = re.sub(r"[^a-z0-9]", "", no_accents.lower())
        return clean_name or "project"

    def _get_next_index(self, directory, prefix):
        max_idx = 0
        if not os.path.exists(directory):
            return 1
        pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)\.[a-zA-Z0-9]+$")
        for fname in os.listdir(directory):
            match = pattern.match(fname)
            if match:
                idx = int(match.group(1))
                if idx > max_idx:
                    max_idx = idx
        return max_idx + 1

    def _build_next_voice_filename(self, target_dir):
        proj_name = self.parent_app.projects.get(self.current_project_id, {}).get("name", "project")
        prefix = self._clean_project_name(proj_name)
        next_idx = self._get_next_index(target_dir, prefix)
        filename = f"{prefix}_{next_idx}.mp3"
        return filename, os.path.join(target_dir, filename)

    def _set_voice_name_display(self):
        if not self.current_project_id or self.current_project_id not in self.parent_app.projects:
            return
        voice_dir = os.path.join(self.parent_app.get_proj_dir(self.current_project_id), "Voices")
        os.makedirs(voice_dir, exist_ok=True)
        filename, _ = self._build_next_voice_filename(voice_dir)
        base = os.path.splitext(filename)[0]
        self.voice_name_entry.config(state="normal")
        self.voice_name_entry.delete(0, tk.END)
        self.voice_name_entry.insert(0, base)
        self.voice_name_entry.config(state="readonly")

    def load_voices(self, clear_only=False):
        for item in self.tree_voices.get_children():
            self.tree_voices.delete(item)

        if clear_only or not self.current_project_id:
            return

        voice_dir = os.path.join(self.parent_app.get_proj_dir(self.current_project_id), "Voices")
        if not os.path.exists(voice_dir):
            return

        files = [f for f in os.listdir(voice_dir) if f.lower().endswith((".mp3", ".wav", ".m4a"))]
        files.sort(key=lambda f: os.path.getmtime(os.path.join(voice_dir, f)), reverse=True)

        p_data = self.parent_app.get_project_data(self.current_project_id)
        usage_map = p_data.get("voice_usage", {}) if isinstance(p_data, dict) else {}

        for fname in files:
            mtime = time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(os.path.join(voice_dir, fname))))
            usage = usage_map.get(fname, 0)
            self.tree_voices.insert("", "end", iid=fname, values=(fname, usage, mtime, "▶️ Nghe | 🗑️ Xóa"))

    def play_voice(self):
        selected = self.tree_voices.selection()
        if not selected:
            return
        fname = selected[0]
        voice_dir = os.path.join(self.parent_app.get_proj_dir(self.current_project_id), "Voices")
        file_path = os.path.join(voice_dir, fname)
        if os.path.exists(file_path):
            os.startfile(file_path)

    def delete_voice(self):
        selected = self.tree_voices.selection()
        if not selected:
            return
        fname = selected[0]
        if not messagebox.askyesno("Xóa", f"Xóa voice '{fname}'?"):
            return
        voice_dir = os.path.join(self.parent_app.get_proj_dir(self.current_project_id), "Voices")
        file_path = os.path.join(voice_dir, fname)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            return messagebox.showerror("Lỗi", f"Không thể xóa file: {e}")

        self.load_voices()
        if hasattr(self.parent_app, "tab1") and getattr(self.parent_app.tab1, "current_project_id", None) == self.current_project_id:
            self.parent_app.tab1.load_voices()

    def _on_voice_action_click(self, event):
        region = self.tree_voices.identify("region", event.x, event.y)
        if region != "cell":
            return
        row_id = self.tree_voices.identify_row(event.y)
        col_id = self.tree_voices.identify_column(event.x)
        if not row_id:
            return
        if col_id != "#4":
            return

        self.tree_voices.selection_set(row_id)
        x, y, width, _ = self.tree_voices.bbox(row_id, col_id)
        if width <= 0:
            return
        offset = event.x - x
        if offset < width / 2:
            self.play_voice()
        else:
            self.delete_voice()

    def start_generate_thread(self):
        if not self.current_project_id:
            return messagebox.showwarning("Thiếu thông tin", "Chưa chọn project!")

        api_key = self.api_key_entry.get().strip()
        content = self.text_input.get("1.0", "end-1c").strip()
        voice_name = ""
        voice_id = self._get_selected_voice_id()

        if not api_key:
            return messagebox.showwarning("Thiếu thông tin", "Sếp chưa nhập API Key!")
        if not content:
            return messagebox.showwarning("Thiếu thông tin", "Sếp chưa nhập nội dung!")
        if not voice_id:
            return messagebox.showwarning("Thiếu thông tin", "Sếp chưa chọn Voice ID!")

        self._save_api_key()

        voice_dir = os.path.join(self.parent_app.get_proj_dir(self.current_project_id), "Voices")
        os.makedirs(voice_dir, exist_ok=True)
        filename, target_path = self._build_next_voice_filename(voice_dir)
        self._set_voice_name_display()

        self.btn_generate.config(state="disabled", text="⌛ ĐANG GHÉP GIỌNG...", bg="#9E9E9E")
        self._set_status(text=f"Đang tạo: {filename}")

        threading.Thread(
            target=self._process_api,
            args=(api_key, content, target_path, filename, self.current_project_id, voice_id),
            daemon=True,
        ).start()

    def _process_api(self, api_key, content, target_path, filename, project_id, voice_id):
        url_post = "https://everai.vn/api/v1/tts"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "response_type": "indirect",
            "callback_url": "https://webhook.site/dummy",
            "input_text": content,
            "voice_code": voice_id,
            "audio_type": "mp3",
            "speed_rate": self.speed_slider.get(),
            "pitch_rate": self.pitch_slider.get(),
            "bitrate": int(self.bitrate_var.get() or 128),
        }

        try:
            response = requests.post(url_post, json=payload, headers=headers)
            if response.status_code != 200:
                self.master.after(0, lambda: messagebox.showerror("Lỗi API", f"Lỗi kết nối Server: {response.text}"))
                return

            res_json = response.json()
            if res_json.get("status") != 1:
                error_msg = res_json.get("error_message", "Lỗi không xác định")
                self.master.after(0, lambda: messagebox.showerror("Lỗi EverAI", f"EverAI từ chối: {error_msg}"))
                return

            request_id = res_json["result"]["request_id"]
            url_get = f"https://everai.vn/api/v1/tts/{request_id}"
            audio_link = None

            for _ in range(60):
                time.sleep(2)
                check_resp = requests.get(url_get, headers=headers)
                if check_resp.status_code == 200:
                    check_data = check_resp.json()
                    if check_data.get("status") == 0:
                        error_msg = check_data.get("error_message", "EverAI trả lỗi")
                        self.master.after(0, lambda msg=error_msg: messagebox.showerror("Lỗi EverAI", msg))
                        return

                    result = check_data.get("result", {}) if isinstance(check_data, dict) else {}
                    status = result.get("status")
                    progress = result.get("progress")
                    audio_expired = result.get("audio_expired")
                    self.master.after(0, lambda rid=request_id, st=status, pg=progress: self._set_progress(rid, st, pg))

                    if status == "done":
                        if audio_expired:
                            self.master.after(0, lambda: messagebox.showerror("Hết hạn", "Audio đã quá hạn lưu trữ, sếp tạo lại nhé!"))
                            return
                        audio_link = result.get("audio_link")
                        break
                    if status in ["error", "failed"]:
                        self.master.after(0, lambda: messagebox.showerror("Lỗi Server", "EverAI bị lỗi khi ghép giọng này!"))
                        return

            if not audio_link:
                self.master.after(0, lambda: messagebox.showerror("Quá giờ", "Chờ EverAI quá lâu, sếp thử lại sau nhé!"))
                return

            audio_data = requests.get(audio_link).content
            with open(target_path, "wb") as f:
                f.write(audio_data)

            self.master.after(0, lambda: messagebox.showinfo("Thành công", f"Đã lưu voice: {filename}"))
            self.master.after(0, self.load_voices)

            if hasattr(self.parent_app, "tab1") and getattr(self.parent_app.tab1, "current_project_id", None) == project_id:
                self.parent_app.tab1.load_voices()

        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("Lỗi hệ thống", f"Vấp dây mạng rồi: {str(e)}"))
        finally:
            self.master.after(0, lambda: self.btn_generate.config(state="normal", text="🚀 TẠO VOICE & LƯU VÀO PROJECT", bg="#4CAF50"))
            self.master.after(0, self._clear_status)

    def _save_api_key(self, event=None):
        api_key = self.api_key_entry.get().strip()
        if api_key:
            self.parent_app.config["everai_key"] = api_key
            self.parent_app.save_config()

    def _schedule_save_api_key(self, event=None):
        if hasattr(self, "_api_key_save_job") and self._api_key_save_job:
            try:
                self.master.after_cancel(self._api_key_save_job)
            except Exception:
                pass
        self._api_key_save_job = self.master.after(500, self._save_api_key)

    def _load_voice_id_candidates(self):
        raw_list = [
            "get-styles?speaker_id=vi_female_thuhien_mb",
            "get-styles?speaker_id=vi_female_thuha_mn",
            "get-styles?speaker_id=vi_male_vanduc_mn",
            "get-styles?speaker_id=vi_female_hacuc_mb",
            "get-styles?speaker_id=vi_female_huyenanh_mb",
            "get-styles?speaker_id=vi_female_kieunhi_mn",
            "get-styles?speaker_id=vi_male_onyx_default",
            "get-styles?speaker_id=vi_female_nova_default",
            "get-styles?speaker_id=vi_male_echo_default",
            "get-styles?speaker_id=vi_male_tuankiet_mn",
            "get-styles?speaker_id=vi_male_giahuy_mb",
            "get-styles?speaker_id=vi_female_khanhlinh_mb",
            "get-styles?speaker_id=vi_male_minhkhang_mb",
            "get-styles?speaker_id=vi_male_minhquan_mb",
            "get-styles?speaker_id=vi_female_hoaian_mb",
            "get-styles?speaker_id=vi_male_ductrong_mb",
            "get-styles?speaker_id=vi_female_khanhhuyentvc_mb",
            "get-styles?speaker_id=vi_male_tridung_mn",
            "get-styles?speaker_id=vi_male_minhtriet_mb",
            "get-styles?speaker_id=vi_male_lehoang_mb",
            "get-styles?speaker_id=vi_female_tramanh_mb",
            "get-styles?speaker_id=vi_female_hongngan_mn",
            "get-styles?speaker_id=vi_female_thuylinh_mb",
            "get-styles?speaker_id=vi_male_thanhtrung_mn",
            "get-styles?speaker_id=vi_female_hoaithuong_mb",
            "get-styles?speaker_id=vi_female_honghanh_mn",
            "get-styles?speaker_id=vi_female_thuytrang_mb",
            "get-styles?speaker_id=vi_male_leduc_mb",
            "get-styles?speaker_id=voice-0638fbcf-9a0c-4924",
            "get-styles?speaker_id=voice-02a1e0b5-bafd-497c",
            "get-styles?speaker_id=voice-26f8d828-405c-4380",
        ]
        ids = []
        seen = set()
        for item in raw_list:
            match = re.search(r"speaker_id=([^&\s]+)", item)
            if not match:
                continue
            voice_id = match.group(1).strip()
            if voice_id and voice_id not in seen:
                seen.add(voice_id)
                ids.append(voice_id)
        return ids

    def _load_voice_aliases(self):
        aliases = self.parent_app.config.get("everai_voice_aliases", {})
        return aliases if isinstance(aliases, dict) else {}

    def _save_voice_aliases(self):
        self.parent_app.config["everai_voice_aliases"] = self.voice_aliases
        self.parent_app.save_config()

    def _is_uuid_voice_id(self, voice_id):
        return str(voice_id).startswith("voice-")

    def _format_voice_label(self, voice_id):
        alias = (self.voice_aliases or {}).get(voice_id, "")
        if alias:
            return f"{alias} | {voice_id}"
        return voice_id

    def _refresh_voice_id_list(self):
        ids = list(self.voice_id_candidates)
        ids.sort(key=lambda v: (0 if self._is_uuid_voice_id(v) else 1, v))
        labels = [self._format_voice_label(vid) for vid in ids]
        self.cb_voice_ids["values"] = labels
        if labels:
            self.cb_voice_ids.current(0)
            self.voice_id_var.set(labels[0])

    def _get_selected_voice_id(self):
        manual = self.voice_id_entry.get().strip()
        if manual:
            return manual
        selected = self.voice_id_var.get().strip()
        if "|" in selected:
            return selected.split("|", 1)[1].strip()
        return selected

    def _rename_voice_id(self):
        voice_id = self._get_selected_voice_id()
        if not voice_id:
            return messagebox.showwarning("Thieu thong tin", "Chua co Voice ID!")
        current = self.voice_aliases.get(voice_id, "")
        new_name = simpledialog.askstring("Dat ten", "Nhap ten cho voice:", initialvalue=current or "")
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            self.voice_aliases.pop(voice_id, None)
        else:
            self.voice_aliases[voice_id] = new_name
        self._save_voice_aliases()
        self._refresh_voice_id_list()

    def _set_status(self, text=""):
        self.lbl_status.config(text=text)

    def _set_progress(self, request_id, status, progress):
        rid_text = f"Request: {request_id}" if request_id else ""
        st_text = f"Trạng thái: {status}" if status else ""
        self.lbl_request.config(text=f"{rid_text}  {st_text}".strip())
        if isinstance(progress, (int, float)):
            self.progress_bar["value"] = max(0, min(100, float(progress)))
            self.lbl_progress.config(text=f"Tiến độ: {float(progress):.0f}%")
        else:
            self.progress_bar["value"] = 0
            self.lbl_progress.config(text="")

    def _clear_status(self):
        self.lbl_status.config(text="")
        self.lbl_request.config(text="")
        self.progress_bar["value"] = 0
        self.lbl_progress.config(text="")

    def _on_voice_drag_select(self, event):
        row_id = self.tree_voices.identify_row(event.y)
        if row_id:
            self.tree_voices.selection_add(row_id)

    def _on_voice_right_click(self, event):
        row_id = self.tree_voices.identify_row(event.y)
        if row_id:
            selected = set(self.tree_voices.selection())
            if row_id not in selected:
                self.tree_voices.selection_set(row_id)
        self._get_voice_menu().tk_popup(event.x_root, event.y_root)

    def _get_voice_menu(self):
        if hasattr(self, "_voice_menu") and self._voice_menu:
            return self._voice_menu
        menu = tk.Menu(self.master, tearoff=0)
        menu.add_command(label="🗑️ Xóa", command=self.delete_voice)
        self._voice_menu = menu
        return menu