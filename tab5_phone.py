import os
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk

from paths import BASE_PATH


class PhoneManagerTab:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.refresh_interval_var = tk.StringVar(value="5")
        self.selected_devices = set(self.main_app.config.get("auto_post_selected_devices", []))
        self.device_map = {}
        self.device_status_map = {}
        self.refresh_job = None
        self.refresh_inflight = False
        self.adb_path = self._resolve_adb_path()

        self.setup_ui()
        self.refresh_devices()

    def setup_ui(self):
        container = tk.Frame(self.parent, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        header = tk.Frame(container, bg="#ffffff", padx=12, pady=10)
        header.pack(fill="x", pady=(0, 10))

        title_wrap = tk.Frame(header, bg="#ffffff")
        title_wrap.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_wrap,
            text="📱 Quản Lý Điện Thoại / Box Phone",
            font=("Arial", 14, "bold"),
            bg="#ffffff",
            fg="#2c3e50",
        ).pack(anchor="w")
        tk.Label(
            title_wrap,
            text="Tool tự quét thiết bị ADB đang cắm máy tính và hiển thị trạng thái kết nối.",
            font=("Arial", 9),
            bg="#ffffff",
            fg="#7f8c8d",
        ).pack(anchor="w", pady=(3, 0))

        action_wrap = tk.Frame(header, bg="#ffffff")
        action_wrap.pack(side="right")

        tk.Button(
            action_wrap,
            text="🔄 Quét ngay",
            bg="#3498db",
            fg="white",
            font=("Arial", 9, "bold"),
            command=self.refresh_devices,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            action_wrap,
            text="☑ Chọn tất cả",
            bg="#16a085",
            fg="white",
            font=("Arial", 9, "bold"),
            command=self.select_all_devices,
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            action_wrap,
            text="☐ Bỏ chọn",
            bg="#7f8c8d",
            fg="white",
            font=("Arial", 9, "bold"),
            command=self.clear_selected_devices,
        ).pack(side="left", padx=(0, 8))

        tk.Checkbutton(
            action_wrap,
            text="Tự quét",
            variable=self.auto_refresh_var,
            bg="#ffffff",
            activebackground="#ffffff",
            font=("Arial", 9, "bold"),
            command=self._toggle_auto_refresh,
        ).pack(side="left")

        tk.Label(action_wrap, text="Chu kỳ:", bg="#ffffff", font=("Arial", 9)).pack(side="left", padx=(10, 5))
        interval_combo = ttk.Combobox(
            action_wrap,
            textvariable=self.refresh_interval_var,
            state="readonly",
            width=4,
            values=("3", "5", "10", "15", "30"),
        )
        interval_combo.pack(side="left")
        interval_combo.bind("<<ComboboxSelected>>", lambda e: self._schedule_refresh())
        tk.Label(action_wrap, text="giây", bg="#ffffff", font=("Arial", 9)).pack(side="left", padx=(5, 0))

        self.lbl_status = tk.Label(
            container,
            text="Chưa quét thiết bị nào.",
            font=("Arial", 10, "bold"),
            bg="#f4f6f9",
            fg="#8e44ad",
        )
        self.lbl_status.pack(anchor="w", pady=(0, 8))

        tree_frame = tk.LabelFrame(
            container,
            text=" Danh Sách Thiết Bị ADB ",
            font=("Arial", 10, "bold"),
            bg="#ffffff",
            padx=10,
            pady=8,
        )
        tree_frame.pack(fill="both", expand=True)

        tree_body = tk.Frame(tree_frame, bg="#ffffff")
        tree_body.pack(fill="both", expand=True)

        columns = ("selected", "serial", "state", "farm_status", "model", "brand", "android", "battery", "transport")
        self.tree = ttk.Treeview(tree_body, columns=columns, show="headings", height=14)
        headings = {
            "selected": "Chọn",
            "serial": "Serial",
            "state": "Trạng thái",
            "farm_status": "Auto đăng",
            "model": "Model",
            "brand": "Hãng",
            "android": "Android",
            "battery": "Pin",
            "transport": "Transport",
        }
        widths = {
            "selected": 70,
            "serial": 190,
            "state": 110,
            "farm_status": 170,
            "model": 170,
            "brand": 110,
            "android": 90,
            "battery": 90,
            "transport": 90,
        }
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="center" if col != "serial" else "w")

        scroll_y = ttk.Scrollbar(tree_body, orient="vertical", command=self.tree.yview)
        scroll_x = ttk.Scrollbar(tree_body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_details)

        detail_frame = tk.LabelFrame(
            container,
            text=" Chi Tiết Thiết Bị ",
            font=("Arial", 10, "bold"),
            bg="#ffffff",
            padx=10,
            pady=8,
        )
        detail_frame.pack(fill="both", expand=False, pady=(10, 0))

        btn_detail = tk.Frame(detail_frame, bg="#ffffff")
        btn_detail.pack(fill="x", pady=(0, 6))
        tk.Button(
            btn_detail,
            text="📋 Copy Serial",
            bg="#16a085",
            fg="white",
            font=("Arial", 9, "bold"),
            command=self.copy_selected_serial,
        ).pack(side="left")

        self.txt_details = tk.Text(detail_frame, height=8, font=("Consolas", 10), bg="#f8f9fa", relief="solid", bd=1)
        self.txt_details.pack(fill="both", expand=True)
        self._set_details_text("Chọn một thiết bị để xem chi tiết.\n\nNếu danh sách trống, kiểm tra cáp USB, driver và lệnh adb trong PATH.")

    def _toggle_auto_refresh(self):
        self._schedule_refresh()

    def _schedule_refresh(self):
        if self.refresh_job:
            try:
                self.parent.after_cancel(self.refresh_job)
            except Exception:
                pass
            self.refresh_job = None

        if self.auto_refresh_var.get():
            try:
                delay_ms = max(3, int(self.refresh_interval_var.get())) * 1000
            except ValueError:
                delay_ms = 5000
            self.refresh_job = self.parent.after(delay_ms, self.refresh_devices)

    def on_tab_activated(self):
        self.refresh_devices()

    def refresh_devices(self):
        if self.refresh_inflight:
            self._schedule_refresh()
            return

        self.adb_path = self._resolve_adb_path()
        self.refresh_inflight = True
        self.lbl_status.config(text="⏳ Đang quét thiết bị ADB...", fg="#e67e22")
        threading.Thread(target=self._scan_devices_worker, daemon=True).start()

    def _scan_devices_worker(self):
        devices = []
        error_text = ""
        try:
            output = self._run_adb_command(["devices", "-l"], timeout=15)
            devices = self._parse_adb_devices(output)
            for device in devices:
                if device["state"] == "device":
                    runtime_info = self._collect_runtime_info(device["serial"])
                    device.update(runtime_info)
                    if not device.get("model"):
                        device["model"] = runtime_info.get("model", "")
                    if not device.get("brand"):
                        device["brand"] = runtime_info.get("brand", "")
        except FileNotFoundError:
            error_text = "❌ Không tìm thấy adb. Bác cài Android Platform Tools rồi thêm adb vào PATH giúp em."
        except subprocess.TimeoutExpired:
            error_text = "❌ ADB phản hồi quá chậm. Kiểm tra lại box phone hoặc thử rút/cắm lại cáp."
        except Exception as exc:
            error_text = f"❌ Lỗi quét thiết bị: {exc}"

        self.parent.after(0, lambda: self._finish_refresh(devices, error_text))

    def _finish_refresh(self, devices, error_text):
        self.refresh_inflight = False
        self.tree.delete(*self.tree.get_children())
        self.device_map = {}

        if error_text:
            self.lbl_status.config(text=error_text, fg="#c0392b")
            self._set_details_text(error_text)
            self._schedule_refresh()
            return

        if not devices:
            self.lbl_status.config(text="⚠️ Chưa phát hiện box phone / điện thoại nào qua ADB.", fg="#d35400")
            self._set_details_text("Danh sách hiện đang trống.\n\nKiểm tra:\n- USB debugging đã bật chưa\n- Máy đã cấp quyền RSA chưa\n- Driver ADB đã đúng chưa")
            self._schedule_refresh()
            return

        active_count = sum(1 for item in devices if item["state"] == "device")
        self.lbl_status.config(
            text=f"✅ Phát hiện {len(devices)} thiết bị, trong đó {active_count} thiết bị sẵn sàng.",
            fg="#27ae60",
        )

        for device in devices:
            serial = device["serial"]
            self.device_map[serial] = device
            farm_status = self.device_status_map.get(serial, "Sẵn sàng" if device.get("state") == "device" else "Chưa sẵn sàng")
            self.tree.insert(
                "",
                "end",
                iid=serial,
                values=(
                    "☑" if serial in self.selected_devices else "☐",
                    serial,
                    device.get("state", ""),
                    farm_status,
                    device.get("model", ""),
                    device.get("brand", ""),
                    device.get("android", ""),
                    device.get("battery", ""),
                    device.get("transport", ""),
                ),
            )

        first_item = self.tree.get_children()
        if first_item:
            self.tree.selection_set(first_item[0])
            self._show_selected_details()

        self._schedule_refresh()

    def _run_adb_command(self, args, serial=None, timeout=10):
        adb_executable = self.adb_path or self._resolve_adb_path()
        if not adb_executable:
            raise FileNotFoundError("adb không tồn tại trong PATH hoặc cạnh tool")

        cmd = [adb_executable]
        if serial:
            cmd.extend(["-s", serial])
        cmd.extend(args)
        creation_flags = 0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
            creationflags=creation_flags,
        )
        if process.returncode != 0:
            message = process.stderr.strip() or process.stdout.strip() or "ADB command failed"
            raise RuntimeError(message)
        return process.stdout

    def _resolve_adb_path(self):
        adb_from_path = shutil.which("adb")
        if adb_from_path:
            return adb_from_path

        candidate_paths = [
            os.path.join(BASE_PATH, "adb.exe"),
            os.path.join(BASE_PATH, "platform-tools", "adb.exe"),
            os.path.join(os.getcwd(), "adb.exe"),
            os.path.join(os.getcwd(), "platform-tools", "adb.exe"),
        ]

        for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            sdk_root = os.environ.get(env_key, "").strip()
            if sdk_root:
                candidate_paths.append(os.path.join(sdk_root, "platform-tools", "adb.exe"))

        for path in candidate_paths:
            if path and os.path.exists(path):
                return path

        return ""

    def _parse_adb_devices(self, raw_output):
        devices = []
        for line in raw_output.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices attached") or line.startswith("*"):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            extras = {}
            for token in parts[2:]:
                if ":" in token:
                    key, value = token.split(":", 1)
                    extras[key] = value

            devices.append(
                {
                    "serial": parts[0],
                    "state": parts[1],
                    "model": extras.get("model", ""),
                    "brand": extras.get("product", ""),
                    "android": "",
                    "battery": "",
                    "transport": extras.get("transport_id", ""),
                    "device_name": extras.get("device", ""),
                    "raw": line,
                }
            )
        return devices

    def _collect_runtime_info(self, serial):
        info = {"brand": "", "model": "", "android": "", "battery": ""}
        try:
            info["brand"] = self._safe_shell_value(serial, ["shell", "getprop", "ro.product.brand"])
            info["model"] = self._safe_shell_value(serial, ["shell", "getprop", "ro.product.model"])
            info["android"] = self._safe_shell_value(serial, ["shell", "getprop", "ro.build.version.release"])
            battery_raw = self._run_adb_command(["shell", "dumpsys", "battery"], serial=serial, timeout=10)
            match = re.search(r"level:\s*(\d+)", battery_raw)
            if match:
                info["battery"] = f"{match.group(1)}%"
        except Exception:
            pass
        return info

    def _safe_shell_value(self, serial, args):
        try:
            return self._run_adb_command(args, serial=serial, timeout=8).strip()
        except Exception:
            return ""

    def _show_selected_details(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        serial = selected[0]
        device = self.device_map.get(serial)
        if not device:
            return

        details = [
            f"Đã chọn    : {'Có' if serial in self.selected_devices else 'Chưa'}",
            f"Serial      : {device.get('serial', '')}",
            f"Trạng thái  : {device.get('state', '')}",
            f"Auto đăng   : {self.device_status_map.get(serial, 'Sẵn sàng')}",
            f"Model       : {device.get('model', '')}",
            f"Hãng        : {device.get('brand', '')}",
            f"Device code : {device.get('device_name', '')}",
            f"Android     : {device.get('android', '')}",
            f"Pin         : {device.get('battery', '')}",
            f"Transport   : {device.get('transport', '')}",
            "",
            "Dòng ADB gốc:",
            device.get("raw", ""),
        ]
        self._set_details_text("\n".join(details))

    def copy_selected_serial(self):
        selected = self.tree.selection()
        if not selected:
            self.lbl_status.config(text="⚠️ Chọn một thiết bị trước khi copy serial.", fg="#d35400")
            return

        serial = selected[0]
        self.parent.clipboard_clear()
        self.parent.clipboard_append(serial)
        self.lbl_status.config(text=f"📋 Đã copy serial: {serial}", fg="#16a085")

    def _set_details_text(self, text):
        self.txt_details.config(state="normal")
        self.txt_details.delete("1.0", tk.END)
        self.txt_details.insert("1.0", text)
        self.txt_details.config(state="disabled")

    def _on_tree_click(self, event):
        row_id = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if row_id and column_id == "#1":
            self.toggle_device_selection(row_id)
            return "break"
        return None

    def toggle_device_selection(self, serial):
        if serial in self.selected_devices:
            self.selected_devices.remove(serial)
        else:
            self.selected_devices.add(serial)

        if self.tree.exists(serial):
            values = list(self.tree.item(serial, "values"))
            if values:
                values[0] = "☑" if serial in self.selected_devices else "☐"
                self.tree.item(serial, values=values)

        self.main_app.config["auto_post_selected_devices"] = sorted(self.selected_devices)
        self.main_app.save_config()
        self._show_selected_details()

    def select_all_devices(self):
        for serial, device in self.device_map.items():
            if device.get("state") == "device":
                self.selected_devices.add(serial)
        self._refresh_selection_marks()

    def clear_selected_devices(self):
        self.selected_devices.clear()
        self._refresh_selection_marks()

    def _refresh_selection_marks(self):
        for serial in self.tree.get_children():
            values = list(self.tree.item(serial, "values"))
            if values:
                values[0] = "☑" if serial in self.selected_devices else "☐"
                self.tree.item(serial, values=values)
        self.main_app.config["auto_post_selected_devices"] = sorted(self.selected_devices)
        self.main_app.save_config()
        self._show_selected_details()

    def get_selected_devices(self):
        return [
            serial
            for serial in self.tree.get_children()
            if serial in self.selected_devices and self.device_map.get(serial, {}).get("state") == "device"
        ]

    def update_device_farm_status(self, serial, status):
        self.device_status_map[serial] = status
        if self.tree.exists(serial):
            values = list(self.tree.item(serial, "values"))
            if len(values) >= 4:
                values[3] = status
                self.tree.item(serial, values=values)
        selected = self.tree.selection()
        if selected and selected[0] == serial:
            self._show_selected_details()