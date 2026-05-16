import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox

from tab2_modules.video_engine import add_cover_to_existing_video


class CoverToolTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.video_paths = []
        self.setup_ui()

    def setup_ui(self):
        container = tk.Frame(self.parent, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=12, pady=12)

        settings = tk.LabelFrame(container, text=" Làm ảnh bìa cho video ngoài ", font=("Arial", 11, "bold"), bg="#ffffff", padx=12, pady=10)
        settings.pack(fill="x")

        row_files = tk.Frame(settings, bg="#ffffff")
        row_files.pack(fill="x", pady=4)
        tk.Button(row_files, text="📹 Chọn video", bg="#3498db", fg="white", font=("Arial", 9, "bold"), command=self.pick_videos).pack(side="left")
        tk.Button(row_files, text="🧹 Xóa danh sách", bg="#7f8c8d", fg="white", font=("Arial", 9, "bold"), command=self.clear_videos).pack(side="left", padx=6)
        self.lbl_count = tk.Label(row_files, text="Chưa chọn video nào", bg="#ffffff", fg="#7f8c8d", font=("Arial", 9, "italic"))
        self.lbl_count.pack(side="left", padx=10)

        row_text = tk.Frame(settings, bg="#ffffff")
        row_text.pack(fill="x", pady=4)
        tk.Label(row_text, text="Chữ trên bìa:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.ent_cover_text = tk.Entry(row_text, width=50, font=("Arial", 10))
        self.ent_cover_text.pack(side="left", padx=6)
        tk.Label(row_text, text="Để trống sẽ dùng tên file video", bg="#ffffff", fg="#7f8c8d", font=("Arial", 9, "italic")).pack(side="left")

        row_out = tk.Frame(settings, bg="#ffffff")
        row_out.pack(fill="x", pady=4)
        tk.Label(row_out, text="Thư mục xuất:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.ent_output_dir = tk.Entry(row_out, width=55, font=("Arial", 10))
        self.ent_output_dir.pack(side="left", padx=6)
        tk.Button(row_out, text="📂 Chọn", bg="#2ecc71", fg="white", font=("Arial", 9, "bold"), command=self.pick_output_dir).pack(side="left")
        tk.Label(row_out, text="Để trống sẽ xuất cạnh file gốc", bg="#ffffff", fg="#7f8c8d", font=("Arial", 9, "italic")).pack(side="left", padx=8)

        row_font = tk.Frame(settings, bg="#ffffff")
        row_font.pack(fill="x", pady=4)
        tk.Label(row_font, text="Font bìa:", bg="#ffffff", font=("Arial", 9, "bold")).pack(side="left")
        self.ent_font = tk.Entry(row_font, width=55, font=("Arial", 10))
        self.ent_font.insert(0, self.main_app.config.get("font_path", ""))
        self.ent_font.pack(side="left", padx=6)
        tk.Button(row_font, text="📂 Chọn Font", bg="#9b59b6", fg="white", font=("Arial", 9, "bold"), command=self.pick_font).pack(side="left")

        self.btn_run = tk.Button(container, text="🚀 LÀM ẢNH BÌA CHO VIDEO ĐÃ CHỌN", bg="#c0392b", fg="white", font=("Arial", 14, "bold"), pady=10, command=self.start_process)
        self.btn_run.pack(fill="x", pady=10)

        log_frame = tk.LabelFrame(container, text=" Log ", font=("Arial", 11, "bold"), bg="#ffffff", padx=12, pady=8)
        log_frame.pack(fill="both", expand=True)
        self.txt_log = tk.Text(log_frame, bg="#1e272e", fg="#2ecc71", font=("Consolas", 10), state="disabled")
        self.txt_log.pack(fill="both", expand=True)

    def add_log(self, message):
        self.main_app.root.after(0, self._insert_log, message)
        self.main_app.log_event("tab15", message, "system")

    def _insert_log(self, message):
        self.txt_log.config(state="normal")
        self.txt_log.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.txt_log.see(tk.END)
        self.txt_log.config(state="disabled")

    def pick_videos(self):
        paths = filedialog.askopenfilenames(
            title="Chọn video cần làm ảnh bìa",
            filetypes=[("Video Files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v"), ("All Files", "*.*")],
        )
        if not paths:
            return
        existing = set(self.video_paths)
        for path in paths:
            if path not in existing:
                self.video_paths.append(path)
                existing.add(path)
        self.lbl_count.config(text=f"Đã chọn {len(self.video_paths)} video")
        self.add_log(f"Đã thêm {len(paths)} video vào danh sách.")

    def clear_videos(self):
        self.video_paths.clear()
        self.lbl_count.config(text="Chưa chọn video nào")
        self.add_log("Đã xóa danh sách video.")

    def pick_output_dir(self):
        folder = filedialog.askdirectory(title="Chọn thư mục xuất video đã có ảnh bìa")
        if folder:
            self.ent_output_dir.delete(0, tk.END)
            self.ent_output_dir.insert(0, folder)

    def pick_font(self):
        font_path = filedialog.askopenfilename(title="Chọn Font", filetypes=[("Font Files", "*.ttf *.otf")])
        if font_path:
            self.ent_font.delete(0, tk.END)
            self.ent_font.insert(0, font_path)
            self.main_app.config["font_path"] = font_path
            self.main_app.save_config()

    def _build_output_path(self, video_path, output_dir):
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        folder = output_dir or os.path.dirname(video_path)
        candidate = os.path.join(folder, f"{base_name}_cover.mp4")
        counter = 1
        while os.path.exists(candidate):
            candidate = os.path.join(folder, f"{base_name}_cover_{counter}.mp4")
            counter += 1
        return candidate

    def start_process(self):
        if not self.video_paths:
            return messagebox.showwarning("Thiếu video", "Bác chọn ít nhất 1 video cần làm ảnh bìa.")

        output_dir = self.ent_output_dir.get().strip()
        if output_dir and not os.path.isdir(output_dir):
            return messagebox.showwarning("Sai thư mục", "Thư mục xuất không tồn tại.")

        self.main_app.config["font_path"] = self.ent_font.get().strip()
        self.main_app.save_config()
        cover_text = self.ent_cover_text.get().strip()
        custom_font = self.ent_font.get().strip()
        self.btn_run.config(state="disabled", text="⏳ ĐANG LÀM ẢNH BÌA...")
        threading.Thread(target=self._run_process, args=(list(self.video_paths), output_dir, cover_text, custom_font), daemon=True).start()

    def _run_process(self, video_paths, output_dir, cover_text, custom_font):
        success = 0

        for video_path in video_paths:
            try:
                if not os.path.exists(video_path):
                    self.add_log(f"❌ Không tìm thấy file: {video_path}")
                    continue

                output_path = self._build_output_path(video_path, output_dir)
                text_for_video = cover_text or os.path.splitext(os.path.basename(video_path))[0]
                self.add_log(f"🎬 Đang làm bìa: {os.path.basename(video_path)}")
                add_cover_to_existing_video(video_path, output_path, text_for_video, custom_font, self.add_log)
                success += 1
                self.add_log(f"✅ Xong: {output_path}")
            except Exception as exc:
                self.add_log(f"❌ Lỗi {os.path.basename(video_path)}: {exc}")

        self.add_log(f"🎉 Hoàn tất: {success}/{len(video_paths)} video.")
        self.main_app.root.after(0, lambda: self.btn_run.config(state="normal", text="🚀 LÀM ẢNH BÌA CHO VIDEO ĐÃ CHỌN"))
