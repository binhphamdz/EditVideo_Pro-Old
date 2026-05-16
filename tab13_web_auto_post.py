import base64
import hashlib
import json
import os
import random
import re
import shutil
import socket
import subprocess
import threading
import time
import tkinter as tk
import urllib.request
import uuid
from tkinter import filedialog, messagebox, ttk

from paths import BASE_PATH
from shopee_export import (
    get_video_output_dir,
    load_tiktok_jobs,
    normalize_shopee_product_link,
    normalize_tiktok_product_link,
    resolve_shopee_video_path,
    update_tiktok_status,
)


class WebLimitReachedError(Exception):
    pass


class WebNeedLoginError(Exception):
    pass


class WebAutoPostTab:
    EXTENSION_APP_ID = "editvideo_pro_tiktok_agent_v1"
    STUDIO_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
    EXTENSION_WS_HOST = "127.0.0.1"
    EXTENSION_WS_PORT = 8765
    EXTENSION_WS_PORTS = list(range(8765, 8786))
    PENDING_STATUSES = ('', 'Chưa chuyển', 'Chưa đăng', 'Sẵn sàng đăng')

    def __init__(self, parent_frame, main_app):
        self.parent = parent_frame
        self.main_app = main_app
        self.parent.config(bg="#f8f9fa")

        self.is_running = False
        self.worker_thread = None
        self.extension_server_started = False
        self.extension_clients = []
        self.extension_client_info = {}
        self.extension_lock = threading.Lock()
        self.extension_requests = {}
        self.extension_ws_port = self.EXTENSION_WS_PORT
        self.log_path = os.path.join(BASE_PATH, "logs", "tab13_web_auto_post.log")
        self.last_post_product_key = ""
        self.scheduler_started = False
        self.extension_watchdog_started = False
        self.last_extension_wake_ts = 0
        self.last_schedule_run_key = ""
        self.auto_schedule_lock = threading.Lock()
        self.auto_schedule_slots = list(self.main_app.config.get("web_auto_schedule_slots", []) or [])

        default_user_data = os.path.join(BASE_PATH, "Browser_Profile", "TikTokWeb")
        self.var_user_data_dir = tk.StringVar(value=str(self.main_app.config.get("web_auto_user_data_dir", default_user_data)))
        self.var_profile_dir = tk.StringVar(value=str(self.main_app.config.get("web_auto_profile_dir", "Default")))
        self.var_headless = tk.BooleanVar(value=bool(self.main_app.config.get("web_auto_headless", False)))
        self.var_debug_port = tk.IntVar(value=int(self.main_app.config.get("web_auto_debug_port", 9222)))
        self.var_attach_product_link = tk.BooleanVar(value=bool(self.main_app.config.get("web_auto_attach_product_link", True)))
        self.var_schedule_enabled = tk.BooleanVar(value=bool(self.main_app.config.get("web_auto_schedule_enabled", False)))
        self.var_schedule_time = tk.StringVar(value=str(self.main_app.config.get("web_auto_schedule_time", "09:00")))
        self.var_schedule_batch_count = tk.IntVar(value=int(self.main_app.config.get("web_auto_schedule_batch_count", 3)))
        self.var_upload_wait = tk.IntVar(value=int(self.main_app.config.get("web_auto_upload_wait", 25)))
        self.var_action_timeout = tk.IntVar(value=int(self.main_app.config.get("web_auto_action_timeout", 25)))
        self.var_extension_receiver = tk.StringVar(value=str(self.main_app.config.get("web_auto_extension_receiver", "Tự chọn")))
        self.var_keep_extension_alive = tk.BooleanVar(value=bool(self.main_app.config.get("web_auto_keep_extension_alive", True)))

        self.setup_ui()
        self._ensure_extension_server()
        self._ensure_scheduler()
        self._ensure_extension_watchdog()
        self.refresh_jobs_preview()

    def setup_ui(self):
        top_frame = tk.Frame(self.parent, bg="#e8f4f8", pady=15, padx=20, bd=1, relief="solid")
        top_frame.pack(fill="x", side="top", pady=10, padx=20)
        tk.Label(
            top_frame,
            text="🌐 TAB 13 - AUTO ĐĂNG WEB TIKTOK (EXTENSION)",
            bg="#e8f4f8",
            font=("Arial", 16, "bold"),
            fg="#1f4e79",
        ).pack(side="left", padx=10)

        self.btn_stop = tk.Button(
            top_frame,
            text="⏹ DỪNG",
            bg="#d9534f",
            fg="white",
            font=("Arial", 12, "bold"),
            command=self.stop_auto_post,
            state="disabled",
            width=12,
        )
        self.btn_stop.pack(side="right", padx=10)

        self.btn_start = tk.Button(
            top_frame,
            text="▶ CHẠY WEB AUTO",
            bg="#28a745",
            fg="white",
            font=("Arial", 12, "bold"),
            command=self.start_auto_post,
            width=18,
        )
        self.btn_start.pack(side="right", padx=10)

        self.status_label = tk.Label(
            self.parent,
            text="💤 Đang chờ lệnh. Tab 13 dùng Chrome đang gắn extension để đăng.",
            fg="#337ab7",
            font=("Arial", 11, "italic", "bold"),
            bg="#f8f9fa",
        )
        self.status_label.pack(pady=5)

        content = tk.PanedWindow(self.parent, orient=tk.HORIZONTAL, sashwidth=6, bg="#f8f9fa")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        left_panel = tk.Frame(content, bg="#f8f9fa")
        right_panel = tk.Frame(content, bg="#f8f9fa")
        content.add(left_panel, minsize=540)
        content.add(right_panel, minsize=500)

        settings = tk.LabelFrame(left_panel, text=" ⚙️ Cấu hình Chrome Extension ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        settings.pack(fill="x", pady=(0, 10))

        row_flags = tk.Frame(settings, bg="#ffffff")
        row_flags.pack(fill="x", pady=6)
        tk.Checkbutton(
            row_flags,
            text="Gắn link sản phẩm/giỏ hàng",
            variable=self.var_attach_product_link,
            bg="#ffffff",
            font=("Arial", 10),
            command=self._save_settings,
        ).pack(side="left")
        tk.Checkbutton(
            row_flags,
            text="Giữ extension online",
            variable=self.var_keep_extension_alive,
            bg="#ffffff",
            font=("Arial", 10),
            command=self._save_settings,
        ).pack(side="left", padx=(16, 0))

        self._build_spin_row(settings, "Chờ upload sau đăng (s):", self.var_upload_wait, 5, 240)
        self._build_spin_row(settings, "Timeout thao tác (s):", self.var_action_timeout, 10, 90)

        schedule = tk.LabelFrame(left_panel, text=" ⏰ Lên lịch đăng ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        schedule.pack(fill="x", pady=(0, 10))
        schedule_row = tk.Frame(schedule, bg="#ffffff")
        schedule_row.pack(fill="x", pady=3)
        tk.Checkbutton(
            schedule_row,
            text="Tự động đăng lúc",
            variable=self.var_schedule_enabled,
            bg="#ffffff",
            font=("Arial", 10),
            command=self._save_settings,
        ).pack(side="left")
        tk.Entry(schedule_row, textvariable=self.var_schedule_time, width=7, font=("Arial", 10), justify="center").pack(side="left", padx=(6, 12))
        tk.Label(schedule_row, text="Số video/lần:", bg="#ffffff", font=("Arial", 10)).pack(side="left")
        tk.Spinbox(schedule_row, textvariable=self.var_schedule_batch_count, from_=1, to=100, width=6, font=("Arial", 10)).pack(side="left", padx=(6, 0))
        tk.Button(schedule_row, text="➕ Thêm lịch tay", bg="#8e44ad", fg="white", font=("Arial", 9, "bold"), command=self.add_manual_schedule_slot).pack(side="left", padx=(8, 0))
        tk.Button(schedule_row, text="🧹 Xóa lịch chờ", bg="#95a5a6", fg="white", font=("Arial", 9, "bold"), command=self.clear_pending_schedule_slots).pack(side="left", padx=(6, 0))
        tk.Label(
            schedule,
            text="Đến giờ, Tab 13 tự lấy job theo thứ tự trộn và đăng lần lượt đủ số lượng đã đặt.",
            bg="#ffffff",
            fg="#636e72",
            justify="left",
            font=("Arial", 9),
        ).pack(fill="x", pady=(4, 0))

        self.lst_schedule_slots = tk.Listbox(schedule, height=4, font=("Arial", 9), bg="#f8f9fa")
        self.lst_schedule_slots.pack(fill="x", pady=(6, 0))
        self.refresh_schedule_slots_view()

        ext_row = tk.Frame(settings, bg="#ffffff")
        ext_row.pack(fill="x", pady=3)
        tk.Label(ext_row, text="Chrome Extension:", bg="#ffffff", font=("Arial", 10), width=18, anchor="w").pack(side="left")
        self.cmb_extension_receiver = ttk.Combobox(ext_row, textvariable=self.var_extension_receiver, values=["Tự chọn"], state="readonly", font=("Arial", 10))
        self.cmb_extension_receiver.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(ext_row, text="↻", width=4, command=self.refresh_extension_clients).pack(side="left")
        tk.Button(ext_row, text="🔌 Kiểm tra/Kích", bg="#1f4e79", fg="white", font=("Arial", 9, "bold"), command=self.check_extension_connection).pack(side="left", padx=(6, 0))

        guide = tk.LabelFrame(left_panel, text=" 🧠 Luồng tab 13 ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        guide.pack(fill="both", expand=True)
        tk.Label(
            guide,
            text=(
                "1) Extension mở tab TikTok Studio Upload trên Chrome đang dùng\n"
                "2) Tool set video, nhập caption\n"
                "3) Nếu bật gắn link: thêm sản phẩm Showcase + gắn giỏ hàng\n"
                "4) Thành công thì DB cập nhật: Đã đăng ✅ WEB"
            ),
            bg="#ffffff",
            justify="left",
            anchor="nw",
            font=("Arial", 10),
        ).pack(fill="both", expand=True)

        jobs_frame = tk.LabelFrame(right_panel, text=" 📋 Danh sách job từ Database ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        jobs_frame.pack(fill="both", expand=True)

        top_jobs = tk.Frame(jobs_frame, bg="#ffffff")
        top_jobs.pack(fill="x", pady=(0, 8))
        self.lbl_job_summary = tk.Label(top_jobs, text="Chưa nạp job.", bg="#ffffff", fg="#8e44ad", font=("Arial", 10, "bold"))
        self.lbl_job_summary.pack(side="left")
        tk.Button(top_jobs, text="🚀 Đăng job đang chọn", bg="#27ae60", fg="white", font=("Arial", 9, "bold"), command=self.post_selected_job).pack(side="right", padx=(6, 0))
        tk.Button(top_jobs, text="🔄 Làm mới", bg="#34495e", fg="white", font=("Arial", 9, "bold"), command=self.refresh_jobs_preview).pack(side="right")

        cols = ("stt", "video", "product", "tiktok", "status")
        self.tree_jobs = ttk.Treeview(jobs_frame, columns=cols, show="headings", height=18)
        self.tree_jobs.heading("stt", text="ID")
        self.tree_jobs.heading("video", text="Tên Video")
        self.tree_jobs.heading("product", text="Tên Sản Phẩm")
        self.tree_jobs.heading("tiktok", text="Link TikTok")
        self.tree_jobs.heading("status", text="Trạng thái")

        self.tree_jobs.column("stt", width=60, anchor="center")
        self.tree_jobs.column("video", width=220, anchor="w")
        self.tree_jobs.column("product", width=170, anchor="w")
        self.tree_jobs.column("tiktok", width=220, anchor="w")
        self.tree_jobs.column("status", width=160, anchor="center")

        self.tree_jobs.tag_configure("done", foreground="#27ae60")
        self.tree_jobs.tag_configure("processing", foreground="#e67e22")
        self.tree_jobs.tag_configure("error", foreground="#c0392b")
        self.tree_jobs.tag_configure("pending", foreground="#2c3e50")

        scroll = ttk.Scrollbar(jobs_frame, orient="vertical", command=self.tree_jobs.yview)
        self.tree_jobs.configure(yscrollcommand=scroll.set)
        self.tree_jobs.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        log_frame = tk.LabelFrame(right_panel, text=" 🧾 Log luồng đăng ", bg="#ffffff", font=("Arial", 10, "bold"), padx=8, pady=6)
        log_frame.pack(fill="x", pady=(10, 0))
        log_actions = tk.Frame(log_frame, bg="#ffffff")
        log_actions.pack(fill="x", pady=(0, 4))
        tk.Button(log_actions, text="Mở file log", bg="#636e72", fg="white", font=("Arial", 9, "bold"), command=self.open_log_file).pack(side="right")
        tk.Button(log_actions, text="Xóa log", bg="#95a5a6", fg="white", font=("Arial", 9, "bold"), command=self.clear_log).pack(side="right", padx=(0, 6))
        self.txt_log = tk.Text(log_frame, height=8, wrap="word", font=("Consolas", 9), bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb")
        self.txt_log.pack(fill="x")
        self.txt_log.config(state="disabled")

        for variable in [self.var_attach_product_link, self.var_keep_extension_alive, self.var_schedule_enabled, self.var_schedule_time, self.var_schedule_batch_count, self.var_upload_wait, self.var_action_timeout, self.var_extension_receiver]:
            variable.trace_add("write", lambda *args: self._save_settings())

    def _build_path_row(self, parent, label, var):
        row = tk.Frame(parent, bg="#ffffff")
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg="#ffffff", font=("Arial", 10), width=18, anchor="w").pack(side="left")
        entry = tk.Entry(row, textvariable=var, font=("Arial", 10))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(row, text="...", width=4, command=self.pick_user_data_dir).pack(side="left")

    def _build_simple_row(self, parent, label, var):
        row = tk.Frame(parent, bg="#ffffff")
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg="#ffffff", font=("Arial", 10), width=18, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, font=("Arial", 10)).pack(side="left", fill="x", expand=True)

    def _build_spin_row(self, parent, label, var, min_val, max_val):
        row = tk.Frame(parent, bg="#ffffff")
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg="#ffffff", font=("Arial", 10), width=18, anchor="w").pack(side="left")
        tk.Spinbox(row, textvariable=var, from_=min_val, to=max_val, width=8, font=("Arial", 10)).pack(side="left")

    def _save_settings(self):
        try:
            self.main_app.config["web_auto_user_data_dir"] = self.var_user_data_dir.get().strip()
            self.main_app.config["web_auto_profile_dir"] = self.var_profile_dir.get().strip() or "Default"
            self.main_app.config["web_auto_headless"] = bool(self.var_headless.get())
            self.main_app.config["web_auto_debug_port"] = int(self.var_debug_port.get())
            self.main_app.config["web_auto_attach_product_link"] = bool(self.var_attach_product_link.get())
            self.main_app.config["web_auto_keep_extension_alive"] = bool(self.var_keep_extension_alive.get())
            self.main_app.config["web_auto_schedule_enabled"] = bool(self.var_schedule_enabled.get())
            self.main_app.config["web_auto_schedule_time"] = self.var_schedule_time.get().strip() or "09:00"
            self.main_app.config["web_auto_schedule_batch_count"] = max(1, int(self.var_schedule_batch_count.get()))
            self.main_app.config["web_auto_upload_wait"] = int(self.var_upload_wait.get())
            self.main_app.config["web_auto_action_timeout"] = int(self.var_action_timeout.get())
            self.main_app.config["web_auto_extension_receiver"] = self.var_extension_receiver.get().strip() or "Tự chọn"
            self.main_app.save_config()
        except Exception:
            pass

    def refresh_extension_clients(self):
        receivers = self._get_live_extension_receivers()
        values = ["Tự chọn"] + receivers
        if hasattr(self, "cmb_extension_receiver") and self.cmb_extension_receiver.winfo_exists():
            self.cmb_extension_receiver["values"] = values
            if self.var_extension_receiver.get() not in values:
                self.var_extension_receiver.set("Tự chọn")

        if receivers:
            self.set_status(f"✅ Extension online: {', '.join(receivers)}", "#27ae60")
        else:
            self.set_status("⚠️ Chưa thấy Chrome extension online. Bấm Kiểm tra/Kích hoặc mở Chrome gắn extension.", "#e67e22")

    def _get_live_extension_receivers(self, max_age_seconds=25):
        now = time.time()
        stale_clients = []
        receivers = set()
        with self.extension_lock:
            for client, info in list(self.extension_client_info.items()):
                if info.get("app_id") != self.EXTENSION_APP_ID:
                    continue
                last_seen = float(info.get("last_seen") or 0)
                if last_seen and now - last_seen > max_age_seconds:
                    stale_clients.append(client)
                    continue
                receiver = str(info.get("receiver") or "").strip()
                if receiver:
                    receivers.add(receiver)

            for client in stale_clients:
                if client in self.extension_clients:
                    self.extension_clients.remove(client)
                self.extension_client_info.pop(client, None)

        for client in stale_clients:
            try:
                client.close()
            except Exception:
                pass

        return sorted(receivers)

    def set_status(self, text, color="#337ab7"):
        if self.status_label.winfo_exists():
            self.status_label.config(text=text, fg=color)

    def add_log(self, message):
        line = f"[{time.strftime('%H:%M:%S')}] {message}"
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

        def append_to_widget():
            if not hasattr(self, "txt_log") or not self.txt_log.winfo_exists():
                return
            self.txt_log.config(state="normal")
            self.txt_log.insert("end", line + "\n")
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")

        try:
            self.parent.after(0, append_to_widget)
        except Exception:
            pass

    def clear_log(self):
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            with open(self.log_path, "w", encoding="utf-8"):
                pass
        except Exception:
            pass
        if hasattr(self, "txt_log") and self.txt_log.winfo_exists():
            self.txt_log.config(state="normal")
            self.txt_log.delete("1.0", "end")
            self.txt_log.config(state="disabled")

    def open_log_file(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", encoding="utf-8"):
                pass
        if os.name == "nt":
            os.startfile(self.log_path)

    def on_tab_activated(self):
        self._ensure_extension_server()
        self._ensure_scheduler()
        self._ensure_extension_watchdog()
        self.refresh_extension_clients()
        self.refresh_jobs_preview()

    def _ensure_scheduler(self):
        if self.scheduler_started:
            return
        self.scheduler_started = True
        threading.Thread(target=self._run_schedule_watcher, daemon=True).start()

    def _ensure_extension_watchdog(self):
        if self.extension_watchdog_started:
            return
        self.extension_watchdog_started = True
        threading.Thread(target=self._run_extension_watchdog, daemon=True).start()

    def _should_keep_extension_alive(self):
        return bool(self.main_app.config.get("web_auto_keep_extension_alive", True))

    def _run_extension_watchdog(self):
        while True:
            try:
                if self._should_keep_extension_alive():
                    self._ensure_extension_server()
                    receivers = self._get_live_extension_receivers()
                    if not receivers and time.time() - self.last_extension_wake_ts >= 300:
                        self.last_extension_wake_ts = time.time()
                        self.add_log("Watchdog: chưa thấy extension online, tự mở Chrome để giữ kết nối.")
                        try:
                            self._open_extension_chrome(show_error=False)
                        except Exception as exc:
                            self.add_log(f"Watchdog không mở được Chrome: {exc}")
                    elif receivers:
                        self.last_extension_wake_ts = 0
                time.sleep(45)
            except Exception as exc:
                try:
                    self.add_log(f"Lỗi watchdog extension: {exc}")
                except Exception:
                    pass
                time.sleep(60)

    def _parse_schedule_time(self):
        raw = self.var_schedule_time.get().strip()
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return None
        return hour, minute

    def _run_schedule_watcher(self):
        while True:
            try:
                if not self.is_running:
                    if self._start_due_auto_schedule_slot():
                        time.sleep(20)
                        continue

                if bool(self.var_schedule_enabled.get()) and not self.is_running:
                    parsed = self._parse_schedule_time()
                    if parsed:
                        hour, minute = parsed
                        now = time.localtime()
                        run_key = time.strftime("%Y-%m-%d", now) + f" {hour:02d}:{minute:02d}"
                        if now.tm_hour == hour and now.tm_min == minute and self.last_schedule_run_key != run_key:
                            self.last_schedule_run_key = run_key
                            count = max(1, int(self.var_schedule_batch_count.get()))
                            self.add_log(f"Đến lịch {hour:02d}:{minute:02d}: tự đăng {count} video.")
                            self.parent.after(0, lambda c=count: self.start_scheduled_post(c))
                    else:
                        self.add_log("Giờ lên lịch không hợp lệ. Dùng định dạng HH:MM, ví dụ 09:30.")
                time.sleep(20)
            except Exception as exc:
                try:
                    self.add_log(f"Lỗi watcher lên lịch: {exc}")
                except Exception:
                    pass
                time.sleep(30)

    def _save_auto_schedule_slots(self):
        with self.auto_schedule_lock:
            slots = list(self.auto_schedule_slots)
        self.main_app.config["web_auto_schedule_slots"] = slots
        try:
            self.main_app.save_config()
        except Exception:
            pass

        try:
            self.parent.after(0, self.refresh_schedule_slots_view)
        except Exception:
            pass

    def refresh_schedule_slots_view(self):
        if not hasattr(self, "lst_schedule_slots") or not self.lst_schedule_slots.winfo_exists():
            return

        self.lst_schedule_slots.delete(0, "end")
        with self.auto_schedule_lock:
            slots = sorted(list(self.auto_schedule_slots), key=lambda item: str(item.get("run_at", "")))

        pending_or_running = [slot for slot in slots if str(slot.get("status", "pending")) in ("pending", "running")]
        if not pending_or_running:
            self.lst_schedule_slots.insert("end", "Chưa có lịch chờ. Bot có thể tự chia lịch, hoặc bác thêm lịch tay tại đây.")
            return

        for slot in pending_or_running:
            source = "BOT" if str(slot.get("source", "")).lower() == "bot" else "TAY"
            status = str(slot.get("status", "pending"))
            run_at = str(slot.get("run_at", ""))
            count = int(slot.get("count") or 1)
            self.lst_schedule_slots.insert("end", f"{run_at} | {count} video | {source} | {status}")

    def _make_unique_schedule_key(self, run_ts):
        with self.auto_schedule_lock:
            used_keys = {str(slot.get("run_at", "")) for slot in self.auto_schedule_slots}

        while True:
            run_key = time.strftime("%Y-%m-%d %H:%M", time.localtime(run_ts))
            if run_key not in used_keys:
                return run_key
            run_ts += 60

    def add_manual_schedule_slot(self):
        parsed = self._parse_schedule_time()
        if not parsed:
            messagebox.showwarning("Giờ không hợp lệ", "Nhập giờ theo định dạng HH:MM, ví dụ 09:30.")
            return

        pending_count = len([job for job in self._load_arranged_jobs() if self._is_pending_job(job)])
        if pending_count <= 0:
            messagebox.showwarning("Không có job", "Tab 13 chưa có video nào đang chờ đăng.")
            return

        try:
            count = max(1, int(self.var_schedule_batch_count.get()))
        except Exception:
            count = 1
        count = min(count, pending_count)

        hour, minute = parsed
        now = time.localtime()
        run_ts = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, minute, 0, now.tm_wday, now.tm_yday, now.tm_isdst))
        if run_ts <= time.time():
            run_ts += 24 * 60 * 60

        slot = {
            "run_at": self._make_unique_schedule_key(run_ts),
            "count": count,
            "status": "pending",
            "source": "manual",
        }
        with self.auto_schedule_lock:
            self.auto_schedule_slots.append(slot)
            self.auto_schedule_slots.sort(key=lambda item: str(item.get("run_at", "")))

        self._save_auto_schedule_slots()
        self.add_log(f"Đã thêm lịch tay {slot['run_at']}: đăng {count} video.")
        self.set_status(f"⏰ Đã thêm lịch tay {slot['run_at'][-5:]} ({count} video)", "#8e44ad")

    def clear_pending_schedule_slots(self):
        with self.auto_schedule_lock:
            before = len(self.auto_schedule_slots)
            self.auto_schedule_slots = [
                slot for slot in self.auto_schedule_slots
                if str(slot.get("status", "pending")) != "pending"
            ]
            removed = before - len(self.auto_schedule_slots)

        self._save_auto_schedule_slots()
        self.add_log(f"Đã xóa {removed} lịch đang chờ.")
        self.set_status(f"🧹 Đã xóa {removed} lịch chờ", "#636e72")

    def _replace_pending_schedule_slots_for_source(self, source, new_slots):
        source_key = str(source or "").lower()
        with self.auto_schedule_lock:
            preserved = [
                slot for slot in self.auto_schedule_slots
                if not (
                    str(slot.get("source", "")).lower() == source_key
                    and str(slot.get("status", "pending")) == "pending"
                )
            ]
            self.auto_schedule_slots = preserved + list(new_slots)
            self.auto_schedule_slots.sort(key=lambda item: str(item.get("run_at", "")))
        self._save_auto_schedule_slots()

    def _start_due_auto_schedule_slot(self):
        now_key = time.strftime("%Y-%m-%d %H:%M", time.localtime())
        due_slot = None
        with self.auto_schedule_lock:
            pending_slots = [slot for slot in self.auto_schedule_slots if str(slot.get("status", "pending")) == "pending"]
            pending_slots.sort(key=lambda item: str(item.get("run_at", "")))
            for slot in pending_slots:
                if str(slot.get("run_at", "")) <= now_key:
                    slot["status"] = "running"
                    due_slot = dict(slot)
                    break
        if not due_slot:
            return False

        self._save_auto_schedule_slots()
        run_at = due_slot.get("run_at", "")
        count = max(1, int(due_slot.get("count") or 1))
        self.add_log(f"Đến lịch tự động {run_at}: đăng {count} video.")
        self.parent.after(0, lambda c=count, k=run_at: self.start_scheduled_post(c, schedule_slot_key=k))
        return True

    def _mark_auto_schedule_slot(self, run_at, status, posted_count=0):
        if not run_at:
            return
        with self.auto_schedule_lock:
            for slot in self.auto_schedule_slots:
                if str(slot.get("run_at", "")) == str(run_at):
                    slot["status"] = status
                    slot["posted_count"] = int(posted_count or 0)
                    break
        self._save_auto_schedule_slots()

    def create_incremental_schedule_after_render(self, source="bot"):
        pending_count = len([job for job in self._load_arranged_jobs() if self._is_pending_job(job)])
        if pending_count <= 0:
            self.add_log(f"Render xong từ {source}: không có job tab 13 nào đang chờ để chia lịch.")
            return []

        now = time.time()
        first_run = now + 5 * 60
        local_now = time.localtime(now)
        end_today = time.mktime((local_now.tm_year, local_now.tm_mon, local_now.tm_mday, 23, 30, 0, local_now.tm_wday, local_now.tm_yday, local_now.tm_isdst))
        slot_counts = []
        remaining = pending_count
        while remaining > 0:
            count = min(remaining, random.randint(1, 3))
            slot_counts.append(count)
            remaining -= count

        available_minutes = max(10, int((end_today - first_run) / 60))
        interval_minutes = max(10, min(60, available_minutes // max(1, len(slot_counts))))

        slots = []
        used_keys = set()
        for index, count in enumerate(slot_counts):
            run_ts = first_run + index * interval_minutes * 60
            run_key = time.strftime("%Y-%m-%d %H:%M", time.localtime(run_ts))
            while run_key in used_keys:
                run_ts += 60
                run_key = time.strftime("%Y-%m-%d %H:%M", time.localtime(run_ts))
            used_keys.add(run_key)
            slots.append({"run_at": run_key, "count": count, "status": "pending", "source": source})

        self._replace_pending_schedule_slots_for_source(source, slots)
        self.var_schedule_batch_count.set(1)
        self._save_settings()
        self.refresh_jobs_preview()
        first_text = slots[0]["run_at"][-5:]
        last_text = slots[-1]["run_at"][-5:]
        self.add_log(f"Đã chia lịch tự động {pending_count} video thành {len(slots)} mốc: từ {first_text} đến {last_text}, mỗi mốc đăng ngẫu nhiên 1-3 video.")
        self.set_status(f"⏰ Đã chia lịch {pending_count} video từ {first_text} đến {last_text}", "#8e44ad")
        return slots

    def schedule_all_pending_after_render(self, source="render"):
        pending_count = len([job for job in self._load_arranged_jobs() if self._is_pending_job(job)])
        if pending_count <= 0:
            self.add_log(f"Render xong từ {source}: không có job tab 13 nào đang chờ để lên lịch.")
            return 0

        if not self._parse_schedule_time():
            self.var_schedule_time.set("09:00")
        self.var_schedule_enabled.set(True)
        self.var_schedule_batch_count.set(pending_count)
        self._save_settings()
        self.refresh_jobs_preview()
        self.add_log(
            f"Render xong từ {source}: đã bật lịch {self.var_schedule_time.get().strip()} "
            f"cho toàn bộ {pending_count} job đang chờ. Thứ tự đăng sẽ trộn để tránh kề cùng sản phẩm."
        )
        self.set_status(f"⏰ Đã lên lịch đăng {pending_count} video lúc {self.var_schedule_time.get().strip()}", "#8e44ad")
        return pending_count

    def pick_user_data_dir(self):
        picked = filedialog.askdirectory(title="Chọn User Data Dir của Chrome")
        if picked:
            self.var_user_data_dir.set(picked)
            self._save_settings()

    def open_profile_dir(self):
        path = self.var_user_data_dir.get().strip()
        if not path:
            return
        os.makedirs(path, exist_ok=True)
        if os.name == "nt":
            os.startfile(path)

    def _detect_chrome_path(self):
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
        ]
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return ""

    def open_manual_login(self):
        self._open_extension_chrome(show_error=True)

    def _open_extension_chrome(self, show_error=False):
        chrome = self._detect_chrome_path()
        if not chrome:
            if show_error:
                messagebox.showerror("Thiếu Chrome", "Không tìm thấy chrome.exe trên máy.")
                return False
            raise RuntimeError("Không tìm thấy chrome.exe trên máy.")

        user_data = self.var_user_data_dir.get().strip()
        profile_dir = self.var_profile_dir.get().strip() or "Default"
        debug_port = int(self.var_debug_port.get())
        os.makedirs(user_data, exist_ok=True)

        args = [
            chrome,
            f"--user-data-dir={user_data}",
            f"--profile-directory={profile_dir}",
            f"--remote-debugging-port={debug_port}",
            self.STUDIO_UPLOAD_URL,
        ]
        self.add_log(f"Mở Chrome gắn extension: profile={profile_dir}, debug_port={debug_port}, user_data={user_data}")
        subprocess.Popen(args)
        self.parent.after(0, lambda: self.set_status("🔐 Đã mở Chrome gắn extension. Nếu Chrome đã mở sẵn, hãy đóng rồi bấm lại để bật debug port.", "#8e44ad"))
        return True

    def check_extension_connection(self):
        self._ensure_extension_server()
        self.refresh_extension_clients()
        receivers = self._get_live_extension_receivers()
        if receivers:
            messagebox.showinfo("Extension online", "Đã thấy extension online:\n" + "\n".join(receivers))
            return

        if not messagebox.askyesno(
            "Chưa thấy extension",
            "Chưa thấy Chrome extension online. Mở Chrome gắn extension/upload page để kích lại kết nối không?",
        ):
            return

        def worker():
            try:
                self._open_extension_chrome(show_error=False)
                receivers = self._wait_for_extension_client(timeout_s=25)
                if receivers:
                    self.parent.after(0, lambda rs=receivers: messagebox.showinfo("Extension online", "Đã kết nối:\n" + "\n".join(rs)))
                else:
                    self.parent.after(0, lambda: messagebox.showwarning("Chưa online", "Đã mở Chrome nhưng extension chưa kết nối. Kiểm tra extension đã bật và reload extension trong chrome://extensions."))
            except Exception as exc:
                self.parent.after(0, lambda e=str(exc): messagebox.showwarning("Không kích được extension", e))

        threading.Thread(target=worker, daemon=True).start()

    def _wait_for_extension_client(self, timeout_s=20):
        deadline = time.time() + max(1, int(timeout_s))
        while time.time() < deadline:
            receivers = self._get_live_extension_receivers()
            if receivers:
                self.parent.after(0, self.refresh_extension_clients)
                return receivers
            time.sleep(1)
        self.parent.after(0, self.refresh_extension_clients)
        return []

    def _ensure_extension_online_or_raise(self, timeout_s=20):
        self._ensure_extension_server()
        receivers = self._get_live_extension_receivers()
        target_receiver = self._get_selected_extension_receiver()
        if target_receiver and target_receiver in receivers:
            return target_receiver
        if not target_receiver and receivers:
            return receivers[0]

        self.add_log("Chưa thấy extension online, tự mở Chrome gắn extension để kích lại kết nối...")
        self._open_extension_chrome(show_error=False)
        receivers = self._wait_for_extension_client(timeout_s=timeout_s)
        target_receiver = self._get_selected_extension_receiver()
        if target_receiver and target_receiver in receivers:
            return target_receiver
        if not target_receiver and receivers:
            return receivers[0]

        raise RuntimeError(
            "Chrome extension chưa online. Hãy kiểm tra: extension EditVideo Pro đã bật trong chrome://extensions, "
            "Chrome đang dùng đúng profile, rồi bấm 'Kiểm tra/Kích' ở Tab 13."
        )

    def _product_key(self, job):
        text = str(job.get("product_name") or job.get("project_name") or job.get("caption") or "").lower()
        text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
        words = [w for w in text.split() if len(w) > 1]
        return " ".join(words[:6]) or str(job.get("stt") or job.get("video_name") or "")

    def _arrange_jobs_mixed(self, jobs):
        groups = {}
        for job in jobs:
            groups.setdefault(self._product_key(job), []).append(job)
        for group in groups.values():
            random.shuffle(group)

        keys = list(groups.keys())
        random.shuffle(keys)
        arranged = []
        last_key = ""
        while keys:
            candidates = [key for key in keys if key != last_key] or keys[:]
            key = max(candidates, key=lambda item: len(groups[item]))
            arranged.append(groups[key].pop(0))
            last_key = key
            if not groups[key]:
                keys.remove(key)
        return arranged

    def _has_adjacent_product_jobs(self, jobs):
        last_key = None
        for job in jobs:
            key = self._product_key(job)
            if last_key and key == last_key:
                return True
            last_key = key
        return False

    def _is_pending_job(self, job):
        return str(job.get("status", "")).strip() in self.PENDING_STATUSES

    def _load_arranged_jobs(self):
        jobs = load_tiktok_jobs(profile_name=self.main_app.get_active_profile_name())
        pending = [job for job in jobs if self._is_pending_job(job)]
        others = [job for job in jobs if not self._is_pending_job(job)]
        return self._arrange_jobs_mixed(pending) + others

    def _claim_next_web_job(self, strict_no_adjacent=False):
        pending = [job for job in self._load_arranged_jobs() if self._is_pending_job(job)]
        if not pending:
            return None

        chosen = pending[0]
        for job in pending:
            if self._product_key(job) != self.last_post_product_key:
                chosen = job
                break
        else:
            if strict_no_adjacent and self.last_post_product_key:
                return {"__blocked_same_product__": True, "blocked_count": len(pending)}

        video_name = chosen.get("video_name", "")
        self._set_job_status(video_name, "Đang xử (WEB)")
        chosen["status"] = "Đang xử (WEB)"
        return chosen

    def refresh_jobs_preview(self):
        for item in self.tree_jobs.get_children():
            self.tree_jobs.delete(item)

        jobs = self._load_arranged_jobs()
        pending_count, processing_count, done_count = 0, 0, 0

        for job in jobs:
            status = str(job.get("status", ""))
            if "Đã đăng" in status:
                tag = "done"
                done_count += 1
            elif "Đang xử" in status:
                tag = "processing"
                processing_count += 1
            elif "Lỗi" in status:
                tag = "error"
            else:
                tag = "pending"
                pending_count += 1

            # Lấy link TikTok từ job nếu có, hoặc từ project data nếu cần
            tiktok_link = job.get("tiktok_link", "")
            self.tree_jobs.insert(
                "",
                "end",
                values=(job.get("stt", ""), job.get("video_name", ""), job.get("product_name", ""), tiktok_link, status),
                tags=(tag,),
            )

        if not jobs:
            self.lbl_job_summary.config(text="Database trống. Chưa có job nào.", fg="#c0392b")
        else:
            self.lbl_job_summary.config(
                text=f"Tổng {len(jobs)} | Chờ đăng: {pending_count} | Đang xử: {processing_count} | Đã đăng: {done_count}",
                fg="#8e44ad",
            )

    def post_selected_job(self):
        selected = self.tree_jobs.selection()
        if not selected:
            messagebox.showwarning("Chưa chọn job", "Bác chọn một job trong bảng trước đã.")
            return

        values = self.tree_jobs.item(selected[0]).get("values", [])
        if len(values) < 2:
            return
        video_name = str(values[1] or "").strip()
        jobs = load_tiktok_jobs(profile_name=self.main_app.get_active_profile_name())
        job = next((item for item in jobs if str(item.get("video_name", "")) == video_name), None)
        if not job:
            messagebox.showwarning("Không thấy job", "Không tìm thấy job này trong database.")
            return
        if not self._is_pending_job(job):
            messagebox.showwarning("Job không sẵn sàng", f"Job đang ở trạng thái: {job.get('status', '')}")
            return

        video_path = resolve_shopee_video_path(video_name)
        if not os.path.exists(video_path):
            messagebox.showwarning("Mất file", "Không thấy file video để đăng.")
            return

        self._start_single_job_worker(job, video_path)

    def start_auto_post(self):
        if self.is_running:
            return

        self._save_settings()
        self.is_running = True
        self.btn_start.config(state="disabled", text="🌐 ĐANG CHẠY WEB")
        self.btn_stop.config(state="normal")
        self.set_status("🚀 Tab 13 đang chạy Web Automation...", "green")
        self.add_log("Bắt đầu chạy auto post từ danh sách job.")

        self.worker_thread = threading.Thread(target=self._run_web_worker, daemon=True)
        self.worker_thread.start()

    def start_scheduled_post(self, batch_count, schedule_slot_key=""):
        if self.is_running:
            self.add_log("Bỏ qua lịch vì Tab 13 đang chạy job khác.")
            return
        self._save_settings()
        pending_jobs = [job for job in self._load_arranged_jobs() if self._is_pending_job(job)]
        if self._has_adjacent_product_jobs(pending_jobs[:max(1, int(batch_count or 1))]):
            self.add_log("Cảnh báo: số job cùng sản phẩm đang nhiều hơn sản phẩm khác, có thể không tránh được kề nhau 100%.")
        self.is_running = True
        self.btn_start.config(state="disabled", text="⏰ ĐANG CHẠY LỊCH")
        self.btn_stop.config(state="normal")
        self.set_status(f"⏰ Đang chạy lịch: {batch_count} video", "#8e44ad")
        self.worker_thread = threading.Thread(target=lambda: self._run_web_worker(limit=batch_count, strict_no_adjacent=True, schedule_slot_key=schedule_slot_key), daemon=True)
        self.worker_thread.start()

    def stop_auto_post(self):
        if not self.is_running:
            return
        self.is_running = False
        self.btn_stop.config(state="disabled")
        self.set_status("⏹ Đang dừng Tab 13...", "#c0392b")
        self.add_log("Đã nhận lệnh dừng Tab 13.")

    def _ensure_extension_server(self):
        if self.extension_server_started:
            return
        self.extension_server_started = True
        self.add_log("Khởi động WebSocket server cho Chrome extension.")
        thread = threading.Thread(target=self._run_extension_ws_server, daemon=True)
        thread.start()

    def _run_extension_ws_server(self):
        server = None
        last_error = None
        for port in self.EXTENSION_WS_PORTS:
            try:
                candidate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                candidate.bind((self.EXTENSION_WS_HOST, port))
                candidate.listen(5)
                server = candidate
                self.extension_ws_port = port
                break
            except Exception as exc:
                last_error = exc
                try:
                    candidate.close()
                except Exception:
                    pass

        if server is None:
            self.extension_server_started = False
            self.add_log(f"Không mở được WebSocket extension: {last_error}")
            self.parent.after(0, lambda e=str(last_error): self.set_status(f"⚠️ Không mở được WS extension: {e[:80]}", "#e67e22"))
            return

        self.add_log(f"Server extension đang nghe ws://127.0.0.1:{self.extension_ws_port}")
        self.parent.after(0, lambda p=self.extension_ws_port: self.set_status(f"✅ Server extension đã bật ở ws://127.0.0.1:{p}", "#27ae60"))

        while True:
            try:
                client, _ = server.accept()
                self.add_log("Có Chrome extension kết nối tới server.")
                threading.Thread(target=self._handle_extension_ws_client, args=(client,), daemon=True).start()
            except Exception:
                time.sleep(0.2)

    def _handle_extension_ws_client(self, client):
        try:
            if not self._ws_handshake(client):
                return
            with self.extension_lock:
                self.extension_clients.append(client)
                self.extension_client_info[client] = {"receiver": "", "last_seen": time.time()}

            while True:
                message = self._ws_recv_text(client)
                if message is None:
                    break
                self._handle_extension_message_for_client(client, message)
        finally:
            with self.extension_lock:
                if client in self.extension_clients:
                    self.extension_clients.remove(client)
                self.extension_client_info.pop(client, None)
            try:
                client.close()
            except Exception:
                pass
            self.add_log("Chrome extension đã ngắt kết nối.")

    def _ws_handshake(self, client):
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = client.recv(4096)
            if not chunk:
                return False
            data += chunk
            if len(data) > 16384:
                return False

        headers = data.decode("utf-8", errors="ignore").split("\r\n")
        key = ""
        for header in headers:
            if header.lower().startswith("sec-websocket-key:"):
                key = header.split(":", 1)[1].strip()
                break
        if not key:
            return False

        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        client.sendall(response.encode("ascii"))
        return True

    def _ws_recv_exact(self, client, size):
        data = b""
        while len(data) < size:
            chunk = client.recv(size - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _ws_recv_text(self, client):
        header = self._ws_recv_exact(client, 2)
        if not header:
            return None

        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            raw_len = self._ws_recv_exact(client, 2)
            if not raw_len:
                return None
            length = int.from_bytes(raw_len, "big")
        elif length == 127:
            raw_len = self._ws_recv_exact(client, 8)
            if not raw_len:
                return None
            length = int.from_bytes(raw_len, "big")

        mask = self._ws_recv_exact(client, 4) if masked else b""
        payload = self._ws_recv_exact(client, length) if length else b""
        if payload is None:
            return None
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))

        if opcode == 8:
            return None
        if opcode != 1:
            return ""
        return payload.decode("utf-8", errors="ignore")

    def _ws_send_text(self, client, message):
        payload = message.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length < 65536:
            header.extend([126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(127)
            header.extend(length.to_bytes(8, "big"))
        client.sendall(bytes(header) + payload)

    def _handle_extension_message_for_client(self, client, message):
        try:
            data = json.loads(message)
        except Exception:
            return

        msg_type = data.get("type")
        if msg_type == "hello":
            receiver = str(data.get("receiver") or "").strip()
            app_id = str(data.get("appId") or data.get("app_id") or "").strip()
            if app_id != self.EXTENSION_APP_ID:
                return
            with self.extension_lock:
                old_info = self.extension_client_info.get(client, {}) if client in self.extension_clients else {}
                if client in self.extension_clients:
                    self.extension_client_info[client] = {"receiver": receiver, "app_id": app_id, "last_seen": time.time()}
            if old_info.get("receiver") != receiver or old_info.get("app_id") != app_id:
                self.add_log(f"Extension online: receiver={receiver or 'chưa có ID'}")
            self.parent.after(0, self.refresh_extension_clients)
            return

        if msg_type not in ("link_done", "post_done", "open_upload_done"):
            return

        request_id = str(data.get("requestId") or data.get("request_id") or "").strip()
        with self.extension_lock:
            req = self.extension_requests.get(request_id)
            if not req:
                return
            req["ok"] = bool(data.get("ok"))
            req["error"] = str(data.get("error") or "")
            req["event"].set()
        self.add_log(f"Extension trả về {msg_type}: ok={bool(data.get('ok'))}, request={request_id[:8]}")

    def _broadcast_extension_message(self, payload, target_receiver=""):
        raw = json.dumps(payload, ensure_ascii=False)
        with self.extension_lock:
            clients = []
            for client in self.extension_clients:
                info = self.extension_client_info.get(client, {})
                if info.get("app_id") != self.EXTENSION_APP_ID:
                    continue
                receiver = info.get("receiver", "")
                if target_receiver and receiver != target_receiver:
                    continue
                clients.append(client)
        sent_count = 0
        for client in clients:
            try:
                self._ws_send_text(client, raw)
                sent_count += 1
            except Exception:
                with self.extension_lock:
                    if client in self.extension_clients:
                        self.extension_clients.remove(client)
                try:
                    client.close()
                except Exception:
                    pass
        return sent_count

    def _get_selected_extension_receiver(self):
        value = self.var_extension_receiver.get().strip()
        if value and value != "Tự chọn":
            return value
        receivers = self._get_live_extension_receivers()
        return receivers[0] if receivers else ""

    def _has_extension_client(self, target_receiver=""):
        receivers = self._get_live_extension_receivers()
        if target_receiver:
            return target_receiver in receivers
        return bool(receivers)

    def _send_product_link_to_extension(self, product_link, timeout_s):
        self._ensure_extension_server()
        request_id = uuid.uuid4().hex
        event = threading.Event()
        with self.extension_lock:
            self.extension_requests[request_id] = {"event": event, "ok": False}

        target_receiver = self._get_selected_extension_receiver()
        if not target_receiver:
            self.refresh_extension_clients()
        payload = {"appId": self.EXTENSION_APP_ID, "url": product_link, "requestId": request_id, "target": target_receiver}
        deadline = time.time() + timeout_s
        self.add_log(f"Gửi link sản phẩm sang extension: target={target_receiver or 'Tự chọn'}, request={request_id[:8]}")
        last_sent_count = None
        try:
            while time.time() < deadline:
                sent_count = self._broadcast_extension_message(payload, target_receiver)
                if sent_count != last_sent_count:
                    self.add_log(f"Đã gửi lệnh thêm sản phẩm tới {sent_count} extension.")
                    last_sent_count = sent_count
                if event.wait(1):
                    break
            else:
                if target_receiver:
                    raise RuntimeError(f"Chrome extension '{target_receiver}' chưa phản hồi. Kiểm tra Chrome đó đang mở Showcase và extension đang kết nối.")
                raise RuntimeError("Chưa có Chrome extension nào phản hồi. Mở Chrome đã cài extension rồi chạy lại.")

            with self.extension_lock:
                result = self.extension_requests.get(request_id, {})
            if not result.get("ok"):
                raise RuntimeError("Extension chưa xác nhận thêm sản phẩm thành công.")
            self.add_log("Extension xác nhận thêm sản phẩm thành công.")
        finally:
            with self.extension_lock:
                self.extension_requests.pop(request_id, None)

    def _send_open_upload_to_extension(self, timeout_s):
        self._ensure_extension_server()
        request_id = uuid.uuid4().hex
        event = threading.Event()
        with self.extension_lock:
            self.extension_requests[request_id] = {"event": event, "ok": False, "error": ""}

        target_receiver = self._get_selected_extension_receiver()
        if not target_receiver:
            self.refresh_extension_clients()
        payload = {
            "type": "open_upload",
            "appId": self.EXTENSION_APP_ID,
            "requestId": request_id,
            "target": target_receiver,
        }
        deadline = time.time() + timeout_s
        self.add_log(f"Yêu cầu extension mở tab upload trên Chrome đang gắn extension: target={target_receiver or 'Tự chọn'}, request={request_id[:8]}")
        last_sent_count = None
        try:
            while time.time() < deadline:
                sent_count = self._broadcast_extension_message(payload, target_receiver)
                if sent_count != last_sent_count:
                    self.add_log(f"Đã gửi lệnh mở upload tới {sent_count} extension.")
                    last_sent_count = sent_count
                if event.wait(1):
                    break
            else:
                if target_receiver:
                    raise RuntimeError(f"Chrome extension '{target_receiver}' chưa phản hồi mở upload.")
                raise RuntimeError("Chưa có Chrome extension nào phản hồi mở upload.")

            with self.extension_lock:
                result = self.extension_requests.get(request_id, {})
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "Extension không mở được tab upload.")
            self.add_log("Extension đã mở/active tab TikTok Studio Upload.")
        finally:
            with self.extension_lock:
                self.extension_requests.pop(request_id, None)

    def _send_full_post_to_extension(self, video_path, caption_text, product_link, attach_product_link, timeout_s):
        self._ensure_extension_server()
        request_id = uuid.uuid4().hex
        event = threading.Event()
        with self.extension_lock:
            self.extension_requests[request_id] = {"event": event, "ok": False, "error": ""}

        target_receiver = self._get_selected_extension_receiver()
        if not target_receiver:
            self.refresh_extension_clients()
        payload = {
            "type": "full_post",
            "appId": self.EXTENSION_APP_ID,
            "url": product_link,
            "videoPath": os.path.abspath(video_path),
            "caption": caption_text or "",
            "attachProductLink": bool(attach_product_link),
            "requestId": request_id,
            "target": target_receiver,
        }
        deadline = time.time() + timeout_s
        try:
            while time.time() < deadline:
                self._broadcast_extension_message(payload, target_receiver)
                if event.wait(1):
                    break
            else:
                if target_receiver:
                    raise RuntimeError(f"Chrome extension '{target_receiver}' chưa phản hồi full post.")
                raise RuntimeError("Chưa có Chrome extension nào phản hồi full post.")

            with self.extension_lock:
                result = self.extension_requests.get(request_id, {})
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "Extension báo đăng video lỗi.")
        finally:
            with self.extension_lock:
                self.extension_requests.pop(request_id, None)

    def _set_job_status(self, video_name, status):
        update_tiktok_status(video_name, status, profile_name=self.main_app.get_active_profile_name())
        self.parent.after(0, self.refresh_jobs_preview)

    def _notify_telegram_post_done(self, video_name, caption_text="", product_link="", attached=False):
        try:
            manager = getattr(self.main_app, "telegram_manager", None)
            if manager and hasattr(manager, "notify_web_post_done"):
                manager.notify_web_post_done(video_name, caption_text, product_link, attached)
        except Exception as exc:
            self.add_log(f"Không gửi được thông báo Telegram: {exc}")

    def _run_web_worker(self, limit=None, strict_no_adjacent=False, schedule_slot_key=""):
        posted_count = 0
        try:
            while self.is_running:
                if limit is not None and posted_count >= limit:
                    self.parent.after(0, lambda c=posted_count: self.set_status(f"✅ Lịch đăng xong {c} video.", "green"))
                    break
                current_job = self._claim_next_web_job(strict_no_adjacent=strict_no_adjacent)
                self.parent.after(0, self.refresh_jobs_preview)
                if current_job and current_job.get("__blocked_same_product__"):
                    blocked_count = int(current_job.get("blocked_count") or 0)
                    self.add_log(f"Dừng lịch để tránh đăng kề cùng sản phẩm. Còn {blocked_count} job sẽ giữ cho lượt sau.")
                    self.parent.after(0, lambda c=blocked_count: self.set_status(f"⏸ Dừng lịch: còn {c} job cùng sản phẩm, giữ cho lượt sau.", "#e67e22"))
                    break
                if not current_job:
                    self.parent.after(0, lambda: self.set_status("🎉 Tab 13 xong hết job.", "green"))
                    break

                video_name = current_job.get("video_name", "")
                video_path = resolve_shopee_video_path(video_name)
                if not os.path.exists(video_path):
                    self._set_job_status(video_name, "Lỗi mất file ❌")
                    self.parent.after(0, lambda vn=video_name: self.set_status(f"❌ Mất file: {vn}", "#c0392b"))
                    continue

                product_link = normalize_tiktok_product_link(current_job.get("tiktok_link", ""))
                caption_text = current_job.get("project_name", "") or current_job.get("caption", "")

                try:
                    self.parent.after(0, lambda vn=video_name: self.set_status(f"🌐 Đang đăng web: {vn}", "#1f4e79"))
                    self.add_log(f"Bắt đầu job: video={video_name}")
                    self._post_single_job(video_path, caption_text, product_link)

                    wait_upload = max(1, int(self.var_upload_wait.get()))
                    for _ in range(wait_upload):
                        if not self.is_running:
                            break
                        time.sleep(1)

                    self._set_job_status(video_name, "Đã đăng ✅ WEB")
                    self._move_video_to_posted_folder(video_path, video_name)
                    self.last_post_product_key = self._product_key(current_job)
                    posted_count += 1
                    self._notify_telegram_post_done(video_name, caption_text, product_link, bool(self.var_attach_product_link.get()) and bool(product_link))
                    self.add_log(f"Hoàn tất job: video={video_name}")
                except WebNeedLoginError:
                    self._set_job_status(video_name, "Chưa đăng")
                    self.add_log("Dừng vì TikTok yêu cầu login/captcha.")
                    self.parent.after(0, lambda: self.set_status("🔐 Cần login/captcha. Mở Chrome Login Tay rồi chạy lại.", "#e67e22"))
                    break
                except Exception as exc:
                    self._set_job_status(video_name, "Chưa đăng")
                    self.add_log(f"Lỗi job {video_name}: {exc}")
                    self.parent.after(0, lambda e=str(exc): self.set_status(f"⚠️ Lỗi web: {e[:80]}", "#e67e22"))
                    time.sleep(2)
        finally:
            if schedule_slot_key:
                self._mark_auto_schedule_slot(schedule_slot_key, "done", posted_count)
            self.is_running = False
            self.parent.after(0, lambda: self.btn_start.config(state="normal", text="▶ CHẠY WEB AUTO"))
            self.parent.after(0, lambda: self.btn_stop.config(state="disabled"))
            self.parent.after(0, self.refresh_jobs_preview)

    def _move_video_to_posted_folder(self, video_path, video_name):
        posted_dir = os.path.join(get_video_output_dir(), "DA_DANG")
        os.makedirs(posted_dir, exist_ok=True)
        target = os.path.join(posted_dir, video_name)
        try:
            if os.path.abspath(video_path) != os.path.abspath(target):
                shutil.move(video_path, target)
                return target
        except Exception:
            pass
        return video_path

    def post_single_video_from_manager(self, video_path, video_name, caption_text, product_link, on_done=None):
        if self.is_running:
            messagebox.showwarning("Tab 13 đang chạy", "Tab 13 đang chạy job khác, bác dừng xong rồi bấm đăng video này lại.")
            return False

        def worker():
            self.is_running = True
            self.parent.after(0, lambda: self.btn_start.config(state="disabled", text="🌐 ĐANG ĐĂNG 1 VIDEO"))
            self.parent.after(0, lambda: self.btn_stop.config(state="normal"))
            try:
                self.parent.after(0, lambda: self.set_status(f"🌐 Đang đăng từ tab quản lý: {video_name}", "#1f4e79"))
                self.add_log(f"Bắt đầu đăng 1 video từ tab quản lý: {video_name}")
                self._set_job_status(video_name, "Đang xử (WEB)")
                self._post_single_job(video_path, caption_text, product_link)
                self._set_job_status(video_name, "Đã đăng ✅ WEB")
                moved_path = self._move_video_to_posted_folder(video_path, video_name)
                self._notify_telegram_post_done(video_name, caption_text, product_link, bool(self.var_attach_product_link.get()) and bool(product_link))
                try:
                    import database
                    database.update_rendered_video_status(video_path, "Đã đăng ✅ WEB")
                    if moved_path != video_path:
                        database.update_rendered_video_path(video_path, moved_path)
                except Exception:
                    pass
                self.parent.after(0, lambda: self.set_status("✅ Đăng xong video từ tab quản lý.", "green"))
                if on_done:
                    self.parent.after(0, lambda: on_done(True, "Đã đăng ✅ WEB"))
            except WebNeedLoginError:
                self._set_job_status(video_name, "Chưa đăng")
                self.add_log("Dừng đăng 1 video vì TikTok yêu cầu login/captcha.")
                self.parent.after(0, lambda: self.set_status("🔐 Cần login/captcha. Mở Chrome Login Tay rồi chạy lại.", "#e67e22"))
                if on_done:
                    self.parent.after(0, lambda: on_done(False, "Cần login/captcha"))
            except Exception as exc:
                self._set_job_status(video_name, "Chưa đăng")
                self.add_log(f"Lỗi đăng 1 video {video_name}: {exc}")
                self.parent.after(0, lambda e=str(exc): self.set_status(f"⚠️ Lỗi web: {e[:80]}", "#e67e22"))
                if on_done:
                    self.parent.after(0, lambda e=str(exc): on_done(False, e))
            finally:
                self.is_running = False
                self.parent.after(0, lambda: self.btn_start.config(state="normal", text="▶ CHẠY WEB AUTO"))
                self.parent.after(0, lambda: self.btn_stop.config(state="disabled"))
                self.parent.after(0, self.refresh_jobs_preview)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _start_single_job_worker(self, job, video_path):
        if self.is_running:
            messagebox.showwarning("Tab 13 đang chạy", "Tab 13 đang chạy job khác, bác dừng xong rồi bấm đăng lại.")
            return False

        video_name = job.get("video_name", "")
        caption_text = job.get("project_name", "") or job.get("caption", "")
        product_link = normalize_tiktok_product_link(job.get("tiktok_link", ""))

        def worker():
            self.is_running = True
            self.parent.after(0, lambda: self.btn_start.config(state="disabled", text="🌐 ĐANG ĐĂNG 1 JOB"))
            self.parent.after(0, lambda: self.btn_stop.config(state="normal"))
            try:
                self._set_job_status(video_name, "Đang xử (WEB)")
                self.parent.after(0, lambda: self.set_status(f"🌐 Đang đăng job đã chọn: {video_name}", "#1f4e79"))
                self.add_log(f"Bắt đầu đăng job đã chọn: {video_name}")
                self._post_single_job(video_path, caption_text, product_link)
                self._set_job_status(video_name, "Đã đăng ✅ WEB")
                self._move_video_to_posted_folder(video_path, video_name)
                self.last_post_product_key = self._product_key(job)
                self._notify_telegram_post_done(video_name, caption_text, product_link, bool(self.var_attach_product_link.get()) and bool(product_link))
                self.parent.after(0, lambda: self.set_status("✅ Đăng xong job đã chọn.", "green"))
            except Exception as exc:
                self._set_job_status(video_name, "Chưa đăng")
                self.add_log(f"Lỗi đăng job đã chọn {video_name}: {exc}")
                self.parent.after(0, lambda e=str(exc): self.set_status(f"⚠️ Lỗi web: {e[:80]}", "#e67e22"))
                self.parent.after(0, lambda e=str(exc): messagebox.showwarning("Đăng lỗi", e[:300]))
            finally:
                self.is_running = False
                self.parent.after(0, lambda: self.btn_start.config(state="normal", text="▶ CHẠY WEB AUTO"))
                self.parent.after(0, lambda: self.btn_stop.config(state="disabled"))
                self.parent.after(0, self.refresh_jobs_preview)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _post_single_job(self, video_path, caption_text, product_link):
        self._ensure_extension_online_or_raise(timeout_s=25)
        product_link = normalize_tiktok_product_link(product_link)
        attach_product_link = bool(self.var_attach_product_link.get()) and bool(product_link)
        if attach_product_link:
            self.add_log("Bước 1/2: thêm sản phẩm vào Showcase bằng Chrome extension.")
            self._phase_add_product_to_showcase(product_link)
        else:
            if bool(self.var_attach_product_link.get()):
                self.add_log("Job không có link TikTok, đăng dạng không gắn link.")
            else:
                self.add_log("Bỏ qua gắn link sản phẩm theo cấu hình.")
        self.add_log("Bước 2/2: extension mở tab upload, set file video và bấm đăng trên chính Chrome đó.")
        self._send_full_post_to_extension(video_path, caption_text, product_link, attach_product_link, max(60, int(self.var_action_timeout.get()) * 30))

    def _ensure_chrome_debug_available(self, cdp_url):
        try:
            with urllib.request.urlopen(cdp_url + "/json/version", timeout=2) as response:
                response.read()
        except Exception as exc:
            raise RuntimeError(
                "Chrome đang gắn extension chưa bật remote debugging. Đóng Chrome đó, bấm 'Mở Chrome gắn Extension' trong Tab 13 rồi chạy lại."
            ) from exc

    def _find_or_open_upload_page(self, context):
        for page in context.pages:
            try:
                if (page.url or "").startswith(self.STUDIO_UPLOAD_URL):
                    page.bring_to_front()
                    return page
            except Exception:
                continue
        page = context.new_page()
        page.goto(self.STUDIO_UPLOAD_URL, wait_until="domcontentloaded")
        return page

    def _phase_add_product_to_showcase(self, product_link):
        self._send_product_link_to_extension(product_link, max(45, int(self.var_action_timeout.get()) * 3))
        time.sleep(1)

    def _phase_upload_and_post(self, page, video_path, caption_text):
        self.add_log(f"Mở TikTok Studio Upload: {self.STUDIO_UPLOAD_URL}")
        page.goto(self.STUDIO_UPLOAD_URL, wait_until="domcontentloaded")
        time.sleep(2)

        if "login" in (page.url or "").lower():
            raise WebNeedLoginError("TikTok yêu cầu login ở trang upload")

        self.add_log(f"Set file video vào input upload: {os.path.basename(video_path)}")
        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(video_path)
        time.sleep(2)

        self.add_log("Nhập caption.")
        self._fill_first_visible(page, [
            "textarea",
            "div[contenteditable='true']",
            "[role='textbox']",
        ], caption_text)

        self.add_log("Bấm Thêm liên kết/Add link.")
        self._click_any(page, [
            "button:has-text('Thêm liên kết')",
            "button:has-text('Add link')",
            "text=Thêm liên kết",
            "text=Add link",
        ])
        time.sleep(1)

        self.add_log("Chọn loại liên kết Sản phẩm/Product.")
        self._click_any(page, [
            "button:has-text('Sản phẩm')",
            "button:has-text('Product')",
            "text=Sản phẩm",
            "text=Product",
        ])
        time.sleep(1)

        add_candidates = [
            page.locator("button:has-text('Thêm')"),
            page.locator("button:has-text('Add')"),
        ]
        if not self._click_first_enabled(add_candidates, timeout_ms=5000):
            raise RuntimeError("Không thấy nút thêm sản phẩm đầu tiên.")
        self.add_log("Đã bấm nút Thêm/Add sản phẩm đầu tiên.")

        time.sleep(1)
        max_wait = 12 * 60
        waited = 0
        post_btn = page.locator('button[data-e2e="post_video_button"]:not([aria-disabled="true"]):not([data-disabled="true"])')
        self.add_log("Đang chờ nút Đăng khả dụng.")
        while waited < max_wait:
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            except Exception:
                pass
            time.sleep(1)
            if post_btn.count() > 0 and post_btn.first.is_enabled():
                break
            waited += 1
        else:
            raise RuntimeError("Không tìm thấy nút Đăng khả dụng!")

        self.add_log("Bấm nút Đăng.")
        post_btn.first.scroll_into_view_if_needed(timeout=5000)
        post_btn.first.click(timeout=5000)
        for _ in range(30):
            if post_btn.count() == 0:
                break
            time.sleep(1)
        time.sleep(5)

    def _click_any(self, page, selectors):
        last_error = None
        for sel in selectors:
            try:
                locator = page.locator(sel).first
                locator.wait_for(state="visible", timeout=5000)
                if not locator.is_enabled():
                    continue
                locator.scroll_into_view_if_needed(timeout=5000)
                locator.click()
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Không tìm thấy nút cần bấm ({selectors[0]}).") from last_error

    def _click_first_enabled(self, locators, timeout_ms=5000):
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            for locator in locators:
                try:
                    count = locator.count()
                    for index in range(count):
                        candidate = locator.nth(index)
                        if candidate.is_visible() and candidate.is_enabled():
                            candidate.scroll_into_view_if_needed(timeout=timeout_ms)
                            candidate.click(timeout=timeout_ms)
                            return True
                except Exception:
                    continue
            time.sleep(0.2)
        return False

    def _fill_first_visible(self, page, selectors, value):
        value = str(value or "").strip()
        if not value:
            return

        for sel in selectors:
            try:
                locator = page.locator(sel).first
                locator.wait_for(state="visible", timeout=4000)
                try:
                    locator.fill(value)
                except Exception:
                    locator.click()
                    page.keyboard.press("Control+A")
                    page.keyboard.type(value)
                return
            except Exception:
                continue
        raise RuntimeError("Không tìm thấy ô nhập liệu phù hợp.")
