import os
import random
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import shutil
import cv2

from paths import BASE_PATH
from shopee_export import (
    claim_next_shopee_job,
    get_video_output_dir,
    load_shopee_jobs,
    normalize_shopee_product_link,
    resolve_shopee_video_path,
    update_shopee_status,
)

try:
    import uiautomator2 as u2
except ImportError:
    u2 = None

class LinkImportError(Exception):
    pass

class LimitReachedError(Exception):
    pass

class AutoPostTab:
    REQUIRED_IMAGE_FILES = [
        "tab_live.png", "icon_canhan.png", "nut_dang_video.png", "chu_thu_vien.png",
        "nut_tiep_theo.png", "nut_tiep_theo_2.png", "o_nhap_mota.png", "nut_dong_y.png",
        "nut_them_san_pham.png", "icon_link.png", "only_link.png", "nut_xoa_tat_ca.png",
        "nut_nhap.png", "chon_tat_ca.png", "nut_them_sp_cuoi.png", "nut_dang_cuoi.png",
    ]
    REMOTE_VIDEO_EXTENSIONS = ("mp4", "mov", "avi", "mkv", "3gp", "webm", "m4v")
    REMOTE_VIDEO_DIRS = ("/sdcard/DCIM/Camera", "/sdcard/DCIM", "/sdcard/Movies", "/sdcard/Download", "/sdcard/Pictures")

    def __init__(self, parent_frame, main_app):
        self.parent = parent_frame
        self.main_app = main_app
        self.parent.config(bg="#f8f9fa")

        self.is_farming = False
        self.is_paused = False
        self.active_workers = 0
        self.active_workers_lock = threading.Lock()

        self.var_stagger = tk.IntVar(value=int(self.main_app.config.get("auto_post_stagger", 15)))
        self.var_click_delay = tk.DoubleVar(value=float(self.main_app.config.get("auto_post_click_delay", 1.0)))
        self.var_upload_wait = tk.IntVar(value=int(self.main_app.config.get("auto_post_upload_wait", 25)))
        self.var_rest_min = tk.IntVar(value=int(self.main_app.config.get("auto_post_rest_min", 8)))
        self.var_rest_max = tk.IntVar(value=int(self.main_app.config.get("auto_post_rest_max", 15)))
        self.var_match_threshold = tk.DoubleVar(value=float(self.main_app.config.get("auto_post_match_threshold", 0.82)))

        self.setup_ui()
        self._bind_settings()
        self.refresh_jobs_preview()

    def setup_ui(self):
        top_frame = tk.Frame(self.parent, bg="#e8f4f8", pady=15, padx=20, bd=1, relief="solid")
        top_frame.pack(fill="x", side="top", pady=10, padx=20)
        tk.Label(top_frame, text="🚜 TRUNG TÂM KIỂM SOÁT AUTO ĐĂNG SHOPEE (DATABASE)", bg="#e8f4f8", font=("Arial", 16, "bold"), fg="#d9534f").pack(side="left", padx=10)

        self.btn_stop = tk.Button(top_frame, text="⏹ DỪNG HẲN", bg="#d9534f", fg="white", font=("Arial", 12, "bold"), command=self.stop_auto_post, state="disabled", width=15)
        self.btn_stop.pack(side="right", padx=10)
        self.btn_pause = tk.Button(top_frame, text="⏸ TẠM DỪNG", bg="#f0ad4e", fg="white", font=("Arial", 12, "bold"), command=self.pause_auto_post, state="disabled", width=15)
        self.btn_pause.pack(side="right", padx=10)
        self.btn_auto = tk.Button(top_frame, text="▶ BẮT ĐẦU AUTO ĐĂNG", bg="#28a745", fg="white", font=("Arial", 12, "bold"), command=self.start_auto_post, width=20)
        self.btn_auto.pack(side="right", padx=10)

        self.manage_status = tk.Label(self.parent, text="🖱️ Hệ thống đã kết nối trực tiếp với Database. Xử lý đa luồng siêu tốc!", fg="#337ab7", font=("Arial", 11, "italic", "bold"), bg="#f8f9fa")
        self.manage_status.pack(pady=5)

        content = tk.PanedWindow(self.parent, orient=tk.HORIZONTAL, sashwidth=6, bg="#f8f9fa")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        left_panel = tk.Frame(content, bg="#f8f9fa")
        right_panel = tk.Frame(content, bg="#f8f9fa")
        content.add(left_panel, minsize=520)
        content.add(right_panel, minsize=520)

        # === CỘT TRÁI ===
        settings_frame = tk.LabelFrame(left_panel, text=" ⚙️ Cấu hình Farm ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        settings_frame.pack(fill="x", pady=(0, 10))

        self._add_setting_row(settings_frame, 0, "Giãn cách máy (s):", self.var_stagger, 3, 120)
        self._add_setting_row(settings_frame, 1, "Delay click (s):", self.var_click_delay, 0.2, 5.0, increment=0.1)
        self._add_setting_row(settings_frame, 2, "Chờ upload sau đăng (s):", self.var_upload_wait, 5, 180)
        self._add_setting_row(settings_frame, 3, "Nghỉ min (s):", self.var_rest_min, 3, 180)
        self._add_setting_row(settings_frame, 4, "Nghỉ max (s):", self.var_rest_max, 3, 300)
        self._add_setting_row(settings_frame, 5, "Ngưỡng khớp ảnh:", self.var_match_threshold, 0.6, 0.98, increment=0.01)

        path_frame = tk.LabelFrame(left_panel, text=" 📁 Nguồn dữ liệu ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        path_frame.pack(fill="x", pady=(0, 10))

        btn_path = tk.Frame(path_frame, bg="#ffffff")
        btn_path.pack(fill="x")
        tk.Button(btn_path, text="📂 Mở kho video", bg="#16a085", fg="white", font=("Arial", 9, "bold"), command=self.open_video_folder).pack(side="left", padx=(0, 8))
        tk.Button(btn_path, text="🖼️ Mở thư mục ảnh", bg="#e67e22", fg="white", font=("Arial", 9, "bold"), command=self.open_image_folder).pack(side="left")

        cv_frame = tk.LabelFrame(left_panel, text=" 🖼️ Trung tâm ảnh mắt thần OpenCV ", bg="#ffffff", font=("Arial", 11, "bold"), fg="#e67e22", padx=15, pady=10)
        cv_frame.pack(fill="both", expand=True)

        tk.Label(cv_frame, text="Hệ thống tự động nhận diện ảnh trong thư mục Phone_image.", bg="#ffffff", fg="#337ab7", font=("Arial", 10, "bold"), justify="left", wraplength=520).pack(anchor="w", pady=(0, 10))

        files_req = "\n".join(f"{idx + 1}. {name}" for idx, name in enumerate(self.REQUIRED_IMAGE_FILES))
        tk.Label(cv_frame, text=f"📌 Danh sách ảnh nên có:\n{files_req}", bg="#f9f9f9", fg="#d35400", font=("Courier New", 9, "bold"), justify="left", anchor="w", padx=10, pady=10).pack(fill="x")

        # === CỘT PHẢI ===
        info_frame = tk.LabelFrame(right_panel, text=" 📋 Danh sách job Shopee ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        info_frame.pack(fill="both", expand=True, pady=(0, 10))

        summary_bar = tk.Frame(info_frame, bg="#ffffff")
        summary_bar.pack(fill="x", pady=(0, 8))
        self.lbl_job_summary = tk.Label(summary_bar, text="Chưa nạp file job.", bg="#ffffff", fg="#8e44ad", font=("Arial", 10, "bold"))
        self.lbl_job_summary.pack(side="left")
        tk.Button(summary_bar, text="🔄 Làm mới danh sách", bg="#34495e", fg="white", font=("Arial", 9, "bold"), command=self.refresh_jobs_preview).pack(side="right")

        cols = ("stt", "video", "product", "status", "action")
        self.tree_jobs = ttk.Treeview(info_frame, columns=cols, show="headings", height=16)
        self.tree_jobs.heading("stt", text="ID")
        self.tree_jobs.heading("video", text="Tên Video")
        self.tree_jobs.heading("product", text="Tên Sản Phẩm")
        self.tree_jobs.heading("status", text="Trạng thái")
        self.tree_jobs.heading("action", text="Chức năng")
        
        self.tree_jobs.column("stt", width=50, anchor="center")
        self.tree_jobs.column("video", width=200, anchor="w")
        self.tree_jobs.column("product", width=150, anchor="w")
        self.tree_jobs.column("status", width=120, anchor="center")
        self.tree_jobs.column("action", width=100, anchor="center")
        
        self.tree_jobs.tag_configure("done", foreground="#27ae60")
        self.tree_jobs.tag_configure("processing", foreground="#e67e22")
        self.tree_jobs.tag_configure("error", foreground="#c0392b")
        self.tree_jobs.tag_configure("pending", foreground="#2c3e50")

        self.tree_jobs.bind("<ButtonRelease-1>", self.on_tree_click)

        job_scroll = ttk.Scrollbar(info_frame, orient="vertical", command=self.tree_jobs.yview)
        self.tree_jobs.configure(yscrollcommand=job_scroll.set)
        self.tree_jobs.pack(side="left", fill="both", expand=True)
        job_scroll.pack(side="right", fill="y")

        guide_frame = tk.LabelFrame(right_panel, text=" Hướng dẫn vận hành ", bg="#ffffff", font=("Arial", 11, "bold"), fg="#8e44ad", padx=15, pady=10)
        guide_frame.pack(fill="x")
        instructions = (
            "✅ BƯỚC 1: Render video ở tab Edit Video để tự tạo Job vào Database.\n"
            "✅ BƯỚC 2: Sang tab Quản Lý Điện Thoại, tick chọn các box phone cần chạy.\n"
            "✅ BƯỚC 3: Kiểm tra thư mục Phone_image đã đủ ảnh mẫu.\n"
            "🚀 BƯỚC 4: Quay lại đây bấm [▶ BẮT ĐẦU AUTO ĐĂNG]."
        )
        tk.Label(guide_frame, text=instructions, bg="#ffffff", font=("Arial", 11), justify="left", anchor="nw").pack(fill="x")

    def _add_setting_row(self, parent, row_idx, label_text, variable, min_val, max_val, increment=1):
        row = tk.Frame(parent, bg="#ffffff")
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label_text, bg="#ffffff", font=("Arial", 10), width=22, anchor="w").pack(side="left")
        spin = tk.Spinbox(row, textvariable=variable, from_=min_val, to=max_val, increment=increment, width=8, font=("Arial", 10))
        spin.pack(side="left")

    def _bind_settings(self):
        bindings = {
            "auto_post_stagger": self.var_stagger,
            "auto_post_click_delay": self.var_click_delay,
            "auto_post_upload_wait": self.var_upload_wait,
            "auto_post_rest_min": self.var_rest_min,
            "auto_post_rest_max": self.var_rest_max,
            "auto_post_match_threshold": self.var_match_threshold,
        }
        for config_key, variable in bindings.items():
            variable.trace_add("write", lambda *args, key=config_key, var=variable: self._save_setting(key, var))

    def _save_setting(self, config_key, variable):
        try:
            self.main_app.config[config_key] = variable.get()
            self.main_app.save_config()
        except Exception: pass

    def on_tab_activated(self):
        self.refresh_jobs_preview()

    def get_phone_image_dir(self):
        folder = os.path.join(BASE_PATH, "Phone_image")
        os.makedirs(folder, exist_ok=True)
        return folder

    def open_image_folder(self):
        folder = self.get_phone_image_dir()
        if os.name == "nt": os.startfile(folder)

    def open_video_folder(self):
        video_output_dir = get_video_output_dir()
        os.makedirs(video_output_dir, exist_ok=True)
        if os.name == "nt": os.startfile(video_output_dir)

    def refresh_jobs_preview(self):
        for item in self.tree_jobs.get_children():
            self.tree_jobs.delete(item)

        jobs = load_shopee_jobs()
        pending_count, processing_count, done_count = 0, 0, 0

        for job in jobs:
            status = job.get("status", "")
            if "Đã đăng" in status: tag = "done"; done_count += 1
            elif "Đang xử" in status: tag = "processing"; processing_count += 1
            elif "Lỗi" in status: tag = "error"
            else: tag = "pending"; pending_count += 1

            self.tree_jobs.insert("", "end", values=(job.get("stt", ""), job.get("video_name", ""), job.get("product_name", ""), status, "[ 📤 Bắn Video ]"), tags=(tag,))

        if not jobs: self.lbl_job_summary.config(text="Database trống. Chưa có job Shopee nào.", fg="#c0392b")
        else: self.lbl_job_summary.config(text=f"Tổng {len(jobs)} job | Chờ đăng: {pending_count} | Đang xử: {processing_count} | Đã đăng: {done_count}", fg="#8e44ad")

    def show_status_temp(self, msg, color="green", duration=3500):
        if hasattr(self, "manage_status") and self.manage_status.winfo_exists():
            self.manage_status.config(text=msg, fg=color)
            if duration > 0: self.parent.after(duration, lambda: self.manage_status.config(text="🖱️ Đang chờ lệnh auto đăng...", fg="#337ab7"))

    def get_adb_path(self):
        if hasattr(self.main_app, "tab5") and getattr(self.main_app.tab5, "adb_path", ""): return self.main_app.tab5.adb_path
        local_adb = os.path.join(BASE_PATH, "adb.exe")
        return local_adb if os.path.exists(local_adb) else "adb"

    def pause_auto_post(self):
        if not self.is_farming: return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.btn_pause.config(text="▶ TIẾP TỤC", bg="#5bc0de")
            self.show_status_temp("⏸ Đã ra lệnh tạm dừng.", "orange", 0)
        else:
            self.btn_pause.config(text="⏸ TẠM DỪNG", bg="#f0ad4e")
            self.show_status_temp("▶ Đã tiếp tục dàn auto đăng.", "green")

    def stop_auto_post(self):
        if not self.is_farming: return
        if messagebox.askyesno("Cảnh báo", "Bác có chắc muốn dừng hẳn hệ thống auto đăng không?"):
            self.is_farming = False
            self.is_paused = False
            self.btn_stop.config(text="⏳ ĐANG DỪNG...", state="disabled")
            self.btn_pause.config(state="disabled")
            self.show_status_temp("⏹ Đang gửi lệnh dừng tới tất cả các máy...", "red", 0)

    def start_auto_post(self):
        if u2 is None: return messagebox.showerror("Thiếu thư viện", "Chưa cài uiautomator2.")

        jobs = load_shopee_jobs()
        if not jobs: return messagebox.showerror("Trống", "Database chưa có video nào. Hãy xuất video trước.")

        selected_devices = self.main_app.tab5.get_selected_devices() if hasattr(self.main_app, "tab5") else []
        if not selected_devices: return messagebox.showwarning("Chưa chọn máy", "Bác chưa tick máy nào ở tab Quản Lý Điện Thoại.")

        self.is_farming = True
        self.is_paused = False
        self.btn_auto.config(state="disabled", text="🚜 ĐANG CHẠY AUTO")
        self.btn_stop.config(state="normal", text="⏹ DỪNG HẲN")
        self.btn_pause.config(state="normal", text="⏸ TẠM DỪNG", bg="#f0ad4e")
        self.show_status_temp(f"🚀 Bắt đầu auto đăng trên {len(selected_devices)} máy.", "green")

        with self.active_workers_lock:
            self.active_workers = len(selected_devices)

        for index, device_id in enumerate(selected_devices):
            self.main_app.tab5.update_device_farm_status(device_id, "🚀 Chuẩn bị xuất kích...")
            delay_time = index * max(0, int(self.var_stagger.get()))
            threading.Thread(target=self._farm_worker_delayed, args=(device_id, delay_time), daemon=True).start()

    def _farm_worker_delayed(self, device_id, delay_time):
        adb_cmd = self.get_adb_path()
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        remote_dir = "/sdcard/DCIM/Camera/"
        current_job = None

        def upd_status(msg): self.parent.after(0, lambda: self.main_app.tab5.update_device_farm_status(device_id, msg))
        def update_job_status(video_name, status):
            update_shopee_status(video_name, status)
            self.parent.after(0, self.refresh_jobs_preview)

        try:
            if delay_time > 0:
                upd_status(f"⏳ Đợi tới lượt ({delay_time}s)")
                for _ in range(delay_time):
                    if not self.is_farming: break
                    time.sleep(1)

            if not self.is_farming: return

            upd_status("🔌 Kết nối U2...")
            device = u2.connect(device_id)
            try: device.set_input_ime(True)
            except: pass
            
            is_app_running = False

            while self.is_farming:
                current_job = None
                while self.is_paused and self.is_farming:
                    upd_status("⏸ Đang tạm dừng...")
                    time.sleep(1)
                if not self.is_farming: break

                upd_status("🔎 Đang bốc job từ Database...")
                current_job = claim_next_shopee_job(device_id[-4:])
                self.parent.after(0, self.refresh_jobs_preview)
                if not current_job:
                    upd_status("🎉 Hoàn thành! (Hết job) -> Về màn hình chính")
                    subprocess.run([adb_cmd, "-s", device_id, "shell", "input", "keyevent", "3"], creationflags=creationflags)
                    break

                video_name = current_job["video_name"]
                caption_text = current_job.get("caption", "")
                link_text = normalize_shopee_product_link(current_job.get("link", ""))
                
                video_path = resolve_shopee_video_path(video_name)
                if not os.path.exists(video_path):
                    vid_path_da_dang = os.path.join(get_video_output_dir(), "DA_DANG", video_name)
                    if os.path.exists(vid_path_da_dang):
                        video_path = vid_path_da_dang
                    else:
                        update_job_status(video_name, "Lỗi mất file ❌")
                        upd_status(f"❌ Mất file: {video_name}")
                        current_job = None
                        time.sleep(1)
                        continue

                file_ext = os.path.splitext(video_path)[1] or ".mp4"
                safe_name = f"auto_shopee_{int(time.time())}{file_ext}"
                temp_remote = f"/sdcard/{safe_name}"
                remote_video_path = self._join_remote_path(remote_dir, safe_name)

                upd_status(f"🧹 Dọn video cũ rồi đẩy {video_name} vào máy...")
                self._clear_remote_videos(adb_cmd, device_id, creationflags, remote_dir=remote_dir, clear_all_dirs=False)
                subprocess.run([adb_cmd, "-s", device_id, "shell", "mkdir", "-p", remote_dir], creationflags=creationflags)

                push_ok = False
                try:
                    result = subprocess.run([adb_cmd, "-s", device_id, "push", video_path, temp_remote], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=120, creationflags=creationflags)
                    if result.returncode == 0:
                        copy_result = subprocess.run([adb_cmd, "-s", device_id, "shell", "cp", temp_remote, remote_video_path], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=30, creationflags=creationflags)
                        if copy_result.returncode == 0:
                            self._broadcast_media_scan(adb_cmd, device_id, remote_video_path, creationflags)
                            time.sleep(2)
                            push_ok = True
                except: pass
                finally: subprocess.run([adb_cmd, "-s", device_id, "shell", "rm", "-f", temp_remote], creationflags=creationflags, check=False)

                if not push_ok:
                    update_job_status(video_name, "Chưa đăng")
                    upd_status("🔁 Đẩy file lỗi, trả job về hàng đợi.")
                    current_job = None
                    time.sleep(2)
                    continue

                try:
                    self._run_post_workflow(device, device_id, adb_cmd, caption_text, link_text, is_app_running, upd_status)
                    is_app_running = True
                except LimitReachedError:
                    update_job_status(video_name, "Chưa đăng")
                    upd_status("🛑 Máy đã chạm giới hạn. Thoát về Home...")
                    self._cleanup_remote_file(adb_cmd, device_id, remote_video_path, creationflags)
                    current_job = None
                    subprocess.run([adb_cmd, "-s", device_id, "shell", "input", "keyevent", "3"], creationflags=creationflags)
                    break
                except Exception as exc:
                    update_job_status(video_name, "Chưa đăng")
                    upd_status(f"❌ Lỗi: {str(exc)[:45]}, trả job về hàng đợi.")
                    self._force_stop_shopee(adb_cmd, device_id, creationflags)
                    is_app_running = False
                    self._cleanup_remote_file(adb_cmd, device_id, remote_video_path, creationflags)
                    current_job = None
                    time.sleep(2)
                    continue

                wait_upload = max(1, int(self.var_upload_wait.get()))
                upd_status(f"⏳ Chờ Upload ({wait_upload}s)...")
                for _ in range(wait_upload):
                    if not self.is_farming: break
                    time.sleep(1)

                update_job_status(video_name, "Đã đăng ✅")
                upd_status("✅ Đăng xong, dọn dẹp file rác.")
                self._cleanup_remote_file(adb_cmd, device_id, remote_video_path, creationflags)
                
                if hasattr(self.main_app, 'posted_today'):
                    self.main_app.posted_today += 1
                    self.main_app.config["posted_today"] = self.main_app.posted_today
                    self.main_app.save_config()
                
                da_dang_folder = os.path.join(get_video_output_dir(), "DA_DANG")
                os.makedirs(da_dang_folder, exist_ok=True)
                try: shutil.move(video_path, os.path.join(da_dang_folder, video_name))
                except: pass
                
                current_job = None

                rest_min = max(1, int(self.var_rest_min.get()))
                rest_max = max(rest_min, int(self.var_rest_max.get()))
                rest_time = random.randint(rest_min, rest_max)
                for remaining in range(rest_time, 0, -1):
                    if not self.is_farming: break
                    upd_status(f"💤 Nghỉ chống spam ({remaining}s)...")
                    time.sleep(1)

            try: device.set_input_ime(False)
            except: pass
        except Exception as exc:
            upd_status(f"❌ Lỗi thiết bị: {str(exc)[:70]}")
        finally:
            if current_job: update_job_status(current_job["video_name"], "Chưa đăng")
            with self.active_workers_lock:
                self.active_workers -= 1
                if self.active_workers <= 0:
                    self.runtime_csv_path = ""
                    self.is_farming = False; self.is_paused = False
                    self.parent.after(0, lambda: self.btn_auto.config(state="normal", text="▶ BẮT ĐẦU AUTO ĐĂNG"))
                    self.parent.after(0, lambda: self.btn_stop.config(state="disabled", text="⏹ DỪNG HẲN"))
                    self.parent.after(0, lambda: self.btn_pause.config(state="disabled", text="⏸ TẠM DỪNG", bg="#f0ad4e"))
            self.parent.after(0, self.refresh_jobs_preview)

    def _run_post_workflow(self, device, device_id, adb_cmd, caption_text, link_text, is_app_running, upd_status):
        creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        def adb_tap(x, y):
            subprocess.run([adb_cmd, "-s", device_id, "shell", "input", "tap", str(x), str(y)], creationflags=creationflags)
            time.sleep(float(self.var_click_delay.get()))

        if not is_app_running:
            upd_status("🚀 Khởi động Shopee từ đầu...")
            self._force_stop_shopee(adb_cmd, device_id, creationflags)
            time.sleep(2)
            device.app_start("com.shopee.vn")
            time.sleep(15)
            self._tap_by_image(device_id, "tab_live.png", timeout=15, fallback=(543, 2024))
            time.sleep(4)

        upd_status("🔍 Đang tìm Icon Cá Nhân (Cho phép vuốt 3 lần)...")
        da_thay_icon = False
        for lan_thu in range(1, 4): 
            try:
                self._tap_by_image(device_id, "icon_canhan.png", conf=0.75, timeout=5)
                da_thay_icon = True
                break 
            except Exception:
                upd_status(f"⚠️ Lóa mắt (Lần {lan_thu}/3). Vuốt đổi video...")
                subprocess.run([adb_cmd, "-s", device_id, "shell", "input", "swipe", "500", "1500", "500", "500", "300"], creationflags=creationflags)
                time.sleep(3) 

        if not da_thay_icon:
            upd_status("⚠️ Vẫn lóa! Dùng tọa độ mù chọc thẳng Icon...")
            w, h = device.window_size()
            tap_x = int(w * 0.093)
            tap_y = int(h * 0.097 if (h / w) < 1.8 else h * 0.075)
            try: adb_tap(tap_x, tap_y)
            except: adb_tap(67, 125)

        time.sleep(3)
        self._tap_by_image(device_id, "nut_dang_video.png", timeout=10)
        time.sleep(3)
        self._tap_by_image(device_id, "chu_thu_vien.png", timeout=10)
        time.sleep(3)

        upd_status("🤖 Đang tích vào ô tròn chọn video...")
        try:
            w, h = device.window_size()
            tap_x = int(w * 0.22) 
            tap_y = int(h * 0.175 if (h / w) < 1.8 else h * 0.165)
            adb_tap(tap_x, tap_y)
        except:
            adb_tap(225, 368) 
        time.sleep(2)

        self._tap_by_image(device_id, "nut_tiep_theo.png", timeout=10)
        time.sleep(4)

        upd_status("⏳ Đang chờ Shopee load video...")
        wait_time = 0
        while wait_time < 180:
            if not self.is_farming: raise Exception("Dừng auto")
            if device(textContains="Đang tải").exists or device(textContains="Uploading").exists:
                time.sleep(2); wait_time += 2
            else:
                time.sleep(3); break

        self._tap_by_image(device_id, "nut_tiep_theo_2.png", timeout=10)
        time.sleep(2)

        upd_status("🔍 Đang tìm ô nhập Caption...")
        try:
            w, h = device.window_size()
            self._tap_by_image(device_id, "o_nhap_mota.png", timeout=6, fallback=(int(w * 0.6), int(h * 0.12)))
        except: adb_tap(int(w * 0.6), int(h * 0.12))
        time.sleep(2)

        upd_status("✍️ Đang gõ Caption...")
        try:
            device.set_fastinput_ime(True)
            device.send_keys(caption_text)
        except: pass
        time.sleep(2)

        upd_status("✅ Đang bấm nút Đồng ý...")
        try:
            w, h = device.window_size()
            self._tap_by_image(device_id, "nut_dong_y.png", timeout=5, fallback=(int(w * 0.90), int(h * 0.07)))
        except: adb_tap(int(w * 0.90), int(h * 0.07))
        time.sleep(2)

        upd_status("🔍 Đang tìm nút Thêm sản phẩm...")
        try:
            w, h = device.window_size()
            tap_x = int(w * 0.72)
            tap_y = int(h * 0.360 if (h / w) < 1.8 else h * 0.355)
            self._tap_by_image(device_id, "nut_them_san_pham.png", conf=0.75, timeout=8, fallback=(tap_x, tap_y))
        except Exception as e:
            adb_tap(int(w * 0.72), int(h * 0.36))
        time.sleep(4) 

        self._tap_by_image(device_id, "icon_link.png", timeout=10)
        time.sleep(2)

        upd_status("🔍 Kiểm tra trạng thái ô nhập Link...")
        try:
            w, h = device.window_size()
            try:
                self._tap_by_image(device_id, "only_link.png", timeout=3)
                time.sleep(1)
                adb_tap(int(w * 0.5), int(h * 0.35))
            except:
                try: self._tap_by_image(device_id, "nut_xoa_tat_ca.png", timeout=5)
                except: adb_tap(int(w * 0.9), int(h * 0.25))
                time.sleep(1)
                adb_tap(int(w * 0.5), int(h * 0.35))
        except: pass
        time.sleep(2)

        upd_status("🔗 Đang dán TOÀN BỘ Link từ Database...")
        try:
            device.set_fastinput_ime(True)
            device.send_keys(link_text)
        except: pass
        time.sleep(2)

        self._tap_by_image(device_id, "nut_nhap.png", timeout=10)
        time.sleep(4)

        try:
            self._tap_by_image(device_id, "chon_tat_ca.png", timeout=8)
            time.sleep(2)
        except Exception as exc:
            raise LinkImportError(str(exc))

        w, h = device.window_size()
        upd_status("✅ Link xịn! Đang thêm vào giỏ...")
        try: self._tap_by_image(device_id, "nut_them_sp_cuoi.png", timeout=8, fallback=(int(w * 0.8), int(h * 0.95)))
        except: adb_tap(int(w * 0.8), int(h * 0.95))
        time.sleep(2)

        upd_status("🌟 Chốt hạ: ĐĂNG VIDEO!")
        try: self._tap_by_image(device_id, "nut_dang_cuoi.png", timeout=8, fallback=(int(w * 0.5), int(h * 0.95)))
        except: adb_tap(int(w * 0.5), int(h * 0.95))
        time.sleep(2)

        try:
            toast_msg = device.toast.get_message(1.0, default="")
            if "too many videos" in toast_msg.lower() or device(textContains="too many videos").exists or device(textContains="Post too many").exists:
                raise LimitReachedError("Shopee báo đạt giới hạn đăng")
        except: pass

    def _tap_by_image(self, device_id, image_name, conf=None, timeout=10, fallback=None):
        image_dir = self.get_phone_image_dir()
        base_name, extension = os.path.splitext(image_name)
        possible_files = [image_name] + [f"{base_name}_{idx}{extension}" for idx in range(2, 6)]
        valid_paths = [os.path.join(image_dir, name) for name in possible_files if os.path.exists(os.path.join(image_dir, name))]
        
        adb_cmd = self.get_adb_path()
        if not valid_paths:
            if fallback:
                subprocess.run([adb_cmd, "-s", device_id, "shell", "input", "tap", str(fallback[0]), str(fallback[1])], creationflags=0x08000000 if os.name == 'nt' else 0)
                return True
            raise FileNotFoundError(f"Thiếu ảnh mẫu {image_name}")

        threshold = float(conf if conf is not None else self.var_match_threshold.get())
        start_time = time.time()
        temp_screen = os.path.join(BASE_PATH, f"temp_cv2_{device_id.replace(':', '_').replace('.', '_')}.png")

        while time.time() - start_time < timeout:
            if not self.is_farming: raise RuntimeError("Dừng auto")
            try:
                subprocess.run([adb_cmd, "-s", device_id, "exec-out", "screencap", "-p"], stdout=open(temp_screen, "wb"), creationflags=0x08000000 if os.name == 'nt' else 0)
                if not os.path.exists(temp_screen) or os.path.getsize(temp_screen) == 0:
                    time.sleep(1); continue

                screen_img = cv2.imread(temp_screen)
                if screen_img is None: time.sleep(1); continue

                for image_path in valid_paths:
                    template = cv2.imread(image_path)
                    if template is None: continue
                    result = cv2.matchTemplate(screen_img, template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    if max_val >= threshold:
                        height, width = template.shape[:2]
                        cx = max_loc[0] + width // 2
                        cy = max_loc[1] + height // 2
                        subprocess.run([adb_cmd, "-s", device_id, "shell", "input", "tap", str(cx), str(cy)], creationflags=0x08000000 if os.name == 'nt' else 0)
                        return True
            finally:
                if os.path.exists(temp_screen):
                    try: os.remove(temp_screen)
                    except: pass
            time.sleep(1)

        if fallback:
            subprocess.run([adb_cmd, "-s", device_id, "shell", "input", "tap", str(fallback[0]), str(fallback[1])], creationflags=0x08000000 if os.name == 'nt' else 0)
            return True
        raise RuntimeError(f"Không tìm thấy ảnh {image_name}")

    def _force_stop_shopee(self, adb_cmd, device_id, creationflags):
        subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "force-stop", "com.shopee.vn"], creationflags=creationflags)

    def _join_remote_path(self, remote_dir, file_name):
        return f"{remote_dir.rstrip('/')}/{file_name}"

    def _get_remote_video_dirs(self, remote_dir=None, clear_all_dirs=True):
        ordered_dirs = []
        candidates = [remote_dir] if not clear_all_dirs else [remote_dir, *self.REMOTE_VIDEO_DIRS]
        for candidate in candidates:
            normalized = str(candidate or "").strip().rstrip("/")
            if normalized and normalized not in ordered_dirs: ordered_dirs.append(normalized)
        return ordered_dirs

    def _clear_remote_videos(self, adb_cmd, device_id, creationflags, remote_dir=None, clear_all_dirs=True):
        remote_dirs = self._get_remote_video_dirs(remote_dir=remote_dir, clear_all_dirs=clear_all_dirs)
        if not remote_dirs: return
        script_parts = []
        for remote_path in remote_dirs:
            patterns = []
            for ext in self.REMOTE_VIDEO_EXTENSIONS:
                patterns.append(f'"{remote_path}"/*.{ext}')
                patterns.append(f'"{remote_path}"/*.{ext.upper()}')
                patterns.append(f'"{remote_path}"/*/*.{ext}')
            script_parts.append("rm -f " + " ".join(patterns))

        subprocess.run([adb_cmd, "-s", device_id, "shell", "sh", "-c", " ; ".join(script_parts)], capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=60, creationflags=creationflags, check=False)
        for remote_path in remote_dirs:
            subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{remote_path}"], creationflags=creationflags, check=False)

    def _broadcast_media_scan(self, adb_cmd, device_id, remote_path, creationflags):
        normalized_path = str(remote_path or "").strip()
        subprocess.run([adb_cmd, "-s", device_id, "shell", "am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", f"file://{normalized_path}"], creationflags=creationflags, check=False)

    def _cleanup_remote_file(self, adb_cmd, device_id, remote_path, creationflags):
        try:
            subprocess.run([adb_cmd, "-s", device_id, "shell", "rm", "-f", f'"{remote_path}"'], creationflags=creationflags, check=False)
            remote_dir = "/sdcard/DCIM/Camera/"
            subprocess.run([adb_cmd, "-s", device_id, "shell", "rm", "-f", f'{remote_dir}*.mp4'], creationflags=creationflags, check=False)
            subprocess.run([adb_cmd, "-s", device_id, "shell", "rm", "-f", f'{remote_dir}*.MOV'], creationflags=creationflags, check=False)
            self._broadcast_media_scan(adb_cmd, device_id, remote_path, creationflags)
            self._broadcast_media_scan(adb_cmd, device_id, remote_dir, creationflags)
        except: pass

    def on_tree_click(self, event):
        if self.is_farming: return 
        region = self.tree_jobs.identify("region", event.x, event.y)
        if region != "cell": return

        column = self.tree_jobs.identify_column(event.x)
        if column == "#5": 
            item_id = self.tree_jobs.identify_row(event.y)
            if item_id:
                values = self.tree_jobs.item(item_id, "values")
                video_name = values[1] 
                self.manual_push_video(video_name)

    def manual_push_video(self, video_name):
        video_path = resolve_shopee_video_path(video_name)
        if not os.path.exists(video_path):
            return messagebox.showerror("Lỗi", f"Không tìm thấy file trên máy tính!\nĐang tìm tại:\n{video_path}")

        selected_devices = []
        if hasattr(self.main_app, "tab5"):
            selected_devices = self.main_app.tab5.get_selected_devices()

        if not selected_devices:
            messagebox.showwarning("Thiếu máy", "Bác chưa tick chọn máy điện thoại nào ở tab Quản Lý Điện Thoại!")
            return

        self.show_status_temp(f"🚀 Đang bắn video {video_name} sang {len(selected_devices)} máy...", "blue", 3000)

        def push_task():
            adb_cmd = self.get_adb_path()
            creationflags = 0x08000000 if os.name == 'nt' else 0
            final_dir = "/sdcard/DCIM/Camera/"

            for device_id in selected_devices:
                try:
                    subprocess.run([adb_cmd, "-s", device_id, "shell", "mkdir", "-p", final_dir], creationflags=creationflags)
                    file_ext = os.path.splitext(video_path)[1] or ".mp4"
                    safe_name = f"manual_{int(time.time())}{file_ext}"
                    temp_remote = f"/sdcard/{safe_name}"
                    final_remote = f"{final_dir}{safe_name}"

                    result = subprocess.run([adb_cmd, "-s", device_id, "push", video_path, temp_remote], capture_output=True, text=True, errors="ignore", timeout=60, creationflags=creationflags)
                    if result.returncode == 0:
                        copy_result = subprocess.run([adb_cmd, "-s", device_id, "shell", "cp", temp_remote, final_remote], capture_output=True, text=True, errors="ignore", timeout=30, creationflags=creationflags)
                        if copy_result.returncode == 0:
                            self._broadcast_media_scan(adb_cmd, device_id, final_remote, creationflags)
                            self.parent.after(0, lambda d=device_id: self.main_app.tab5.update_device_farm_status(d, f"✅ Bắn tay xong: {video_name}"))
                        else:
                            self.parent.after(0, lambda d=device_id: self.main_app.tab5.update_device_farm_status(d, "❌ Copy nội bộ thất bại."))
                    else:
                        self.parent.after(0, lambda d=device_id: self.main_app.tab5.update_device_farm_status(d, "❌ Bắn tay thất bại."))
                except Exception as e:
                    print(f"Lỗi bắn tay: {e}")
                finally:
                    subprocess.run([adb_cmd, "-s", device_id, "shell", "rm", "-f", temp_remote], creationflags=creationflags, check=False)

            self.parent.after(0, lambda: messagebox.showinfo("Hoàn tất", f"Đã bắn xong video vào {len(selected_devices)} máy!\nMở Shopee lên là thấy ngay!"))
            
        threading.Thread(target=push_task, daemon=True).start()