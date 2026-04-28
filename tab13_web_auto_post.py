import os
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from paths import BASE_PATH
from shopee_export import (
    claim_next_shopee_job,
    get_video_output_dir,
    load_shopee_jobs,
    normalize_shopee_product_link,
    resolve_shopee_video_path,
    update_shopee_status,
)


class WebLimitReachedError(Exception):
    pass


class WebNeedLoginError(Exception):
    pass


class WebAutoPostTab:
    SHOP_SHOWCASE_URL = "https://shop.tiktok.com/streamer/showcase/product/list"
    STUDIO_UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"

    def __init__(self, parent_frame, main_app):
        self.parent = parent_frame
        self.main_app = main_app
        self.parent.config(bg="#f8f9fa")

        self.is_running = False
        self.worker_thread = None

        default_user_data = os.path.join(BASE_PATH, "Browser_Profile", "TikTokWeb")
        self.var_user_data_dir = tk.StringVar(value=str(self.main_app.config.get("web_auto_user_data_dir", default_user_data)))
        self.var_profile_dir = tk.StringVar(value=str(self.main_app.config.get("web_auto_profile_dir", "Default")))
        self.var_headless = tk.BooleanVar(value=bool(self.main_app.config.get("web_auto_headless", False)))
        self.var_upload_wait = tk.IntVar(value=int(self.main_app.config.get("web_auto_upload_wait", 25)))
        self.var_action_timeout = tk.IntVar(value=int(self.main_app.config.get("web_auto_action_timeout", 25)))

        self.setup_ui()
        self.refresh_jobs_preview()

    def setup_ui(self):
        top_frame = tk.Frame(self.parent, bg="#e8f4f8", pady=15, padx=20, bd=1, relief="solid")
        top_frame.pack(fill="x", side="top", pady=10, padx=20)
        tk.Label(
            top_frame,
            text="🌐 TAB 13 - AUTO ĐĂNG WEB TIKTOK (PLAYWRIGHT)",
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
            text="💤 Đang chờ lệnh. Tab 13 chạy bằng browser profile để giữ đăng nhập.",
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

        settings = tk.LabelFrame(left_panel, text=" ⚙️ Cấu hình Browser Profile ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        settings.pack(fill="x", pady=(0, 10))

        self._build_path_row(settings, "User Data Dir:", self.var_user_data_dir)
        self._build_simple_row(settings, "Profile Dir Name:", self.var_profile_dir)

        row_flags = tk.Frame(settings, bg="#ffffff")
        row_flags.pack(fill="x", pady=6)
        tk.Checkbutton(
            row_flags,
            text="Chạy headless (ẩn browser)",
            variable=self.var_headless,
            bg="#ffffff",
            font=("Arial", 10),
            command=self._save_settings,
        ).pack(side="left")

        self._build_spin_row(settings, "Chờ upload sau đăng (s):", self.var_upload_wait, 5, 240)
        self._build_spin_row(settings, "Timeout thao tác (s):", self.var_action_timeout, 10, 90)

        action_row = tk.Frame(settings, bg="#ffffff")
        action_row.pack(fill="x", pady=(8, 0))
        tk.Button(
            action_row,
            text="🧭 Mở Profile Folder",
            bg="#636e72",
            fg="white",
            font=("Arial", 9, "bold"),
            command=self.open_profile_dir,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            action_row,
            text="🔐 Mở Chrome Login Tay",
            bg="#8e44ad",
            fg="white",
            font=("Arial", 9, "bold"),
            command=self.open_manual_login,
        ).pack(side="left")

        guide = tk.LabelFrame(left_panel, text=" 🧠 Luồng tab 13 ", bg="#ffffff", font=("Arial", 11, "bold"), padx=15, pady=10)
        guide.pack(fill="both", expand=True)
        tk.Label(
            guide,
            text=(
                "1) Vào TikTok Shop Showcase -> bấm 'URL sản phẩm' -> nhập link sản phẩm\n"
                "2) Vào TikTok Studio Upload -> up video -> nhập caption\n"
                "3) Thêm liên kết -> Sản phẩm -> chọn sản phẩm đầu tiên -> Đăng\n"
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
        tk.Button(top_jobs, text="🔄 Làm mới", bg="#34495e", fg="white", font=("Arial", 9, "bold"), command=self.refresh_jobs_preview).pack(side="right")

        cols = ("stt", "video", "product", "status")
        self.tree_jobs = ttk.Treeview(jobs_frame, columns=cols, show="headings", height=18)
        self.tree_jobs.heading("stt", text="ID")
        self.tree_jobs.heading("video", text="Tên Video")
        self.tree_jobs.heading("product", text="Tên Sản Phẩm")
        self.tree_jobs.heading("status", text="Trạng thái")

        self.tree_jobs.column("stt", width=60, anchor="center")
        self.tree_jobs.column("video", width=220, anchor="w")
        self.tree_jobs.column("product", width=170, anchor="w")
        self.tree_jobs.column("status", width=160, anchor="center")

        self.tree_jobs.tag_configure("done", foreground="#27ae60")
        self.tree_jobs.tag_configure("processing", foreground="#e67e22")
        self.tree_jobs.tag_configure("error", foreground="#c0392b")
        self.tree_jobs.tag_configure("pending", foreground="#2c3e50")

        scroll = ttk.Scrollbar(jobs_frame, orient="vertical", command=self.tree_jobs.yview)
        self.tree_jobs.configure(yscrollcommand=scroll.set)
        self.tree_jobs.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        for variable in [self.var_user_data_dir, self.var_profile_dir, self.var_upload_wait, self.var_action_timeout]:
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
            self.main_app.config["web_auto_upload_wait"] = int(self.var_upload_wait.get())
            self.main_app.config["web_auto_action_timeout"] = int(self.var_action_timeout.get())
            self.main_app.save_config()
        except Exception:
            pass

    def set_status(self, text, color="#337ab7"):
        if self.status_label.winfo_exists():
            self.status_label.config(text=text, fg=color)

    def on_tab_activated(self):
        self.refresh_jobs_preview()

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
        chrome = self._detect_chrome_path()
        if not chrome:
            return messagebox.showerror("Thiếu Chrome", "Không tìm thấy chrome.exe trên máy.")

        user_data = self.var_user_data_dir.get().strip()
        profile_dir = self.var_profile_dir.get().strip() or "Default"
        os.makedirs(user_data, exist_ok=True)

        args = [
            chrome,
            f"--user-data-dir={user_data}",
            f"--profile-directory={profile_dir}",
            self.STUDIO_UPLOAD_URL,
            self.SHOP_SHOWCASE_URL,
        ]
        subprocess.Popen(args)
        self.set_status("🔐 Đã mở Chrome profile. Bác login tay 1 lần rồi chạy auto.", "#8e44ad")

    def refresh_jobs_preview(self):
        for item in self.tree_jobs.get_children():
            self.tree_jobs.delete(item)

        jobs = load_shopee_jobs()
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

            self.tree_jobs.insert(
                "",
                "end",
                values=(job.get("stt", ""), job.get("video_name", ""), job.get("product_name", ""), status),
                tags=(tag,),
            )

        if not jobs:
            self.lbl_job_summary.config(text="Database trống. Chưa có job nào.", fg="#c0392b")
        else:
            self.lbl_job_summary.config(
                text=f"Tổng {len(jobs)} | Chờ đăng: {pending_count} | Đang xử: {processing_count} | Đã đăng: {done_count}",
                fg="#8e44ad",
            )

    def start_auto_post(self):
        if self.is_running:
            return

        self._save_settings()
        self.is_running = True
        self.btn_start.config(state="disabled", text="🌐 ĐANG CHẠY WEB")
        self.btn_stop.config(state="normal")
        self.set_status("🚀 Tab 13 đang chạy Web Automation...", "green")

        self.worker_thread = threading.Thread(target=self._run_web_worker, daemon=True)
        self.worker_thread.start()

    def stop_auto_post(self):
        if not self.is_running:
            return
        self.is_running = False
        self.btn_stop.config(state="disabled")
        self.set_status("⏹ Đang dừng Tab 13...", "#c0392b")

    def _set_job_status(self, video_name, status):
        update_shopee_status(video_name, status)
        self.parent.after(0, self.refresh_jobs_preview)

    def _run_web_worker(self):
        try:
            while self.is_running:
                current_job = claim_next_shopee_job("WEB")
                self.parent.after(0, self.refresh_jobs_preview)
                if not current_job:
                    self.parent.after(0, lambda: self.set_status("🎉 Tab 13 xong hết job.", "green"))
                    break

                video_name = current_job.get("video_name", "")
                video_path = resolve_shopee_video_path(video_name)
                if not os.path.exists(video_path):
                    self._set_job_status(video_name, "Lỗi mất file ❌")
                    self.parent.after(0, lambda vn=video_name: self.set_status(f"❌ Mất file: {vn}", "#c0392b"))
                    continue

                product_link = normalize_shopee_product_link(current_job.get("link", ""))
                caption_text = current_job.get("caption", "")

                try:
                    self.parent.after(0, lambda vn=video_name: self.set_status(f"🌐 Đang đăng web: {vn}", "#1f4e79"))
                    self._post_single_job(video_path, caption_text, product_link)

                    wait_upload = max(1, int(self.var_upload_wait.get()))
                    for _ in range(wait_upload):
                        if not self.is_running:
                            break
                        time.sleep(1)

                    self._set_job_status(video_name, "Đã đăng ✅ WEB")
                    self._move_video_to_posted_folder(video_path, video_name)
                except WebNeedLoginError:
                    self._set_job_status(video_name, "Chưa đăng")
                    self.parent.after(0, lambda: self.set_status("🔐 Cần login/captcha. Mở Chrome Login Tay rồi chạy lại.", "#e67e22"))
                    break
                except Exception as exc:
                    self._set_job_status(video_name, "Chưa đăng")
                    self.parent.after(0, lambda e=str(exc): self.set_status(f"⚠️ Lỗi web: {e[:80]}", "#e67e22"))
                    time.sleep(2)
        finally:
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
        except Exception:
            pass

    def _post_single_job(self, video_path, caption_text, product_link):
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError(
                "Thiếu Playwright. Cài: pip install playwright ; playwright install chromium"
            ) from exc

        user_data = self.var_user_data_dir.get().strip()
        profile_dir = self.var_profile_dir.get().strip() or "Default"
        headless = bool(self.var_headless.get())
        timeout_ms = max(10, int(self.var_action_timeout.get())) * 1000

        if not user_data:
            raise RuntimeError("Thiếu User Data Dir cho Chrome profile.")
        os.makedirs(user_data, exist_ok=True)

        with sync_playwright() as p:
            launch_kwargs = {
                "user_data_dir": user_data,
                "headless": headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    f"--profile-directory={profile_dir}",
                ],
            }

            context = None
            try:
                try:
                    context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
                except Exception:
                    context = p.chromium.launch_persistent_context(**launch_kwargs)

                context.set_default_timeout(timeout_ms)
                page = context.new_page()

                self._phase_add_product_to_showcase(page, product_link)
                self._phase_upload_and_post(page, video_path, caption_text)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(f"Timeout thao tác web: {exc}") from exc
            finally:
                if context is not None:
                    context.close()

    def _phase_add_product_to_showcase(self, page, product_link):
        page.goto(self.SHOP_SHOWCASE_URL, wait_until="domcontentloaded")
        time.sleep(1)

        if "login" in (page.url or "").lower():
            raise WebNeedLoginError("TikTok yêu cầu login ở trang Showcase")

        # 1. Bấm nút Thêm sản phẩm mới
        self._click_any(page, [
            "button[data-tid='m4b_button']:has-text('Thêm sản phẩm mới')",
            "button:has-text('Thêm sản phẩm mới')",
        ])
        time.sleep(0.5)

        # 2. Điền link vào input đúng placeholder
        self._fill_first_visible(page, [
            "input[data-tid='m4b_input'][placeholder*='URL sản phẩm']",
            "input[placeholder*='URL sản phẩm']",
        ], product_link)
        time.sleep(0.2)

        # 3. Bấm nút URL sản phẩm để load
        self._click_any(page, [
            "button[data-tid='m4b_button']:has-text('URL sản phẩm')",
            "button:has-text('URL sản phẩm')",
        ])
        time.sleep(1.2)

        # 4. Kiểm tra sản phẩm đã hiện ra trong bảng
        table = page.locator("[data-tid='m4b_table'] table tbody tr")
        if table.count() < 1:
            raise RuntimeError("Không tìm thấy sản phẩm nào sau khi nhập link. Kiểm tra lại link hoặc selector.")

        # 5. Bấm nút Thêm sản phẩm
        self._click_any(page, [
            "button.pc_add_product:has-text('Thêm sản phẩm')",
            "button:has-text('Thêm sản phẩm')",
        ])
        time.sleep(2)

    def _phase_upload_and_post(self, page, video_path, caption_text):
        page.goto(self.STUDIO_UPLOAD_URL, wait_until="domcontentloaded")
        time.sleep(2)

        if "login" in (page.url or "").lower():
            raise WebNeedLoginError("TikTok yêu cầu login ở trang upload")

        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(video_path)
        time.sleep(2)

        self._fill_first_visible(page, [
            "textarea",
            "div[contenteditable='true']",
            "[role='textbox']",
        ], caption_text)

        self._click_any(page, [
            "button:has-text('Thêm liên kết')",
            "button:has-text('Add link')",
            "text=Thêm liên kết",
            "text=Add link",
        ])
        time.sleep(1)

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
        clicked = False
        for loc in add_candidates:
            if loc.count() > 0:
                loc.first.click(timeout=5000)
                clicked = True
                break
        if not clicked:
            raise RuntimeError("Không thấy nút thêm sản phẩm đầu tiên.")

        time.sleep(1)
        self._click_any(page, [
            "button:has-text('Đăng')",
            "button:has-text('Post')",
            "button:has-text('Publish')",
            "text=Đăng",
            "text=Post",
        ])
        time.sleep(3)

    def _click_any(self, page, selectors):
        last_error = None
        for sel in selectors:
            try:
                locator = page.locator(sel).first
                locator.wait_for(state="visible", timeout=5000)
                locator.click()
                return
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"Không tìm thấy nút cần bấm ({selectors[0]}).") from last_error

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
