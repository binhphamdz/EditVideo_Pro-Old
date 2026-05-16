import os
import time
import random
import threading
import csv
import shutil
import requests
from datetime import datetime
import concurrent.futures
import telebot
from paths import DEFAULT_PROFILE, get_export_dir

VOICE_FILE_EXTS = ('.mp3', '.wav', '.m4a', '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v')

class TelegramBotManager:
    def __init__(self, main_app):
        self.main_app = main_app
        self.bot = None
        self.bot_is_running = False
        self.bot_sessions = {}
        self.session_lock = threading.Lock()  # 🔒 Thread-safety cho sessions
        self.render_batch_lock = threading.Lock()
        self.render_status_lock = threading.Lock()
        self.current_render_batch = None
        self.waiting_render_batches = []
        self.notify_chat_ids = set(self.main_app.config.get("telegram_notify_chat_ids", []))

    def register_notify_chat(self, chat_id):
        try:
            chat_id = int(chat_id)
        except Exception:
            return
        self.notify_chat_ids.add(chat_id)
        try:
            self.main_app.config["telegram_notify_chat_ids"] = sorted(self.notify_chat_ids)
            self.main_app.save_config()
        except Exception:
            pass

    def notify_web_post_done(self, video_name, caption="", product_link="", attached=False):
        if not self.bot or not self.notify_chat_ids:
            return
        link_status = "có gắn giỏ" if attached else "không gắn giỏ"
        text = (
            "✅ Đã đăng xong video TikTok\n"
            f"🎬 {video_name}\n"
            f"🛒 {link_status}"
        )
        if caption:
            text += f"\n📝 {str(caption)[:120]}"
        if product_link and attached:
            text += f"\n🔗 {product_link}"
        for chat_id in list(self.notify_chat_ids):
            try:
                self.bot.send_message(chat_id, text)
            except Exception as exc:
                print(f"⚠️ Không gửi được thông báo Telegram post_done tới {chat_id}: {exc}")

    def get_active_profile_name(self):
        try:
            return self.main_app.get_active_profile_name()
        except Exception:
            return DEFAULT_PROFILE

    def get_live_output_dir(self):
        return get_export_dir(self.get_active_profile_name())

    def get_available_profiles(self):
        try:
            return self.main_app.get_available_profiles()
        except Exception:
            return [self.get_active_profile_name()]

    def switch_profile_from_bot(self, chat_id, target_profile):
        target_profile = str(target_profile or "").strip()
        if not target_profile:
            if self.bot:
                self.bot.send_message(chat_id, "❌ Bác chưa chọn tài khoản đích.")
            return

        if self.render_batch_lock.locked():
            if self.bot:
                self.bot.send_message(chat_id, "⛔ Đang render batch, tạm khóa đổi tài khoản để tránh lệch thư mục xuất video. Xong render rồi đổi tiếp nhé sếp.")
            return

        def do_switch():
            try:
                current_profile = self.get_active_profile_name()
                if target_profile == current_profile:
                    self.bot.send_message(chat_id, f"ℹ️ Bot đang đứng sẵn ở tài khoản {current_profile} rồi sếp.")
                    return

                self.main_app.switch_profile(target_profile, show_notice=False)
                self.clear_sessions()
                self.bot.send_message(chat_id, f"✅ Đã chuyển bot sang tài khoản {target_profile} thành công.")
            except Exception as exc:
                self.bot.send_message(chat_id, f"❌ Không đổi được tài khoản: {exc}")

        if hasattr(self.main_app, 'root') and self.main_app.root:
            self.main_app.root.after(0, do_switch)
        else:
            do_switch()

    def rename_profile_from_bot(self, chat_id, old_profile, new_profile_name):
        def do_rename():
            try:
                ok, msg = self.main_app.rename_profile(old_profile, new_profile_name)
                self.clear_sessions()
                prefix = "✅" if ok else "❌"
                self.bot.send_message(chat_id, f"{prefix} {msg}")
            except Exception as exc:
                self.bot.send_message(chat_id, f"❌ Không đổi tên được tài khoản: {exc}")

        if hasattr(self.main_app, 'root') and self.main_app.root:
            self.main_app.root.after(0, do_rename)
        else:
            do_rename()

    def clear_sessions(self):
        with self.session_lock:
            self.bot_sessions.clear()

    def stop_telegram_bot(self):
        if self.bot:
            try: self.bot.stop_polling()
            except: pass
        self.clear_sessions()
        self.bot_is_running = False
        self.main_app.bot_is_running = False 

    def restart_telegram_bot(self):
        self.stop_telegram_bot()
        time.sleep(1)
        self.start_telegram_bot()

    def get_bot_stats(self):
        import database
        from datetime import datetime

        total = today = da_chuyen = chua_chuyen = 0
        today_str = datetime.now().strftime('%Y-%m-%d')
        raw_lines = []

        try:
            rows = database.get_all_rendered_videos(self.get_active_profile_name())
            for row in rows:
                total += 1
                created = str(row['created_at'])[:10]  # "YYYY-MM-DD"
                if created == today_str:
                    today += 1
                status = (row['status'] or "Chưa chuyển").strip()
                if "Đã" in status:
                    da_chuyen += 1
                else:
                    chua_chuyen += 1
                raw_lines.append(f"{row['created_at']},{row['project_name']},{row['voice_name']},{row['file_path']},{status}")
        except Exception as e:
            print("Lỗi đọc stats từ DB:", e)

        return total, today, da_chuyen, chua_chuyen, raw_lines

    def get_voice_usage(self):
        """Lấy số lần sử dụng từng Voice từ Database"""
        import database
        usage = {}
        try:
            with database.db_lock:
                conn = database.get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        p.name as project_name,
                        v.file_name,
                        v.usage_count,
                        CASE
                            WHEN v.last_used IS NOT NULL
                            AND v.last_used > datetime('now', '-1 days', 'localtime')
                            THEN 1 ELSE 0
                        END as recently_used
                    FROM voices v JOIN projects p ON v.project_id = p.id
                """)
                for row in cursor.fetchall():
                    key = f"{row['project_name']}_{row['file_name']}"
                    recent_penalty = 1000000 if int(row['recently_used'] or 0) else 0
                    usage[key] = int(row['usage_count'] or 0) + recent_penalty
                conn.close()
        except: pass
        return usage

    def pick_least_used_voices(self, project_name, voices, voice_usage_db, count):
        """Chọn voice ít dùng trước tuyệt đối, chỉ random trong nhóm cùng số lần dùng."""
        if not voices or count <= 0:
            return []

        picks_needed = min(count, len(voices))
        usage_pairs = []
        for voice_name in voices:
            usage = voice_usage_db.get(f"{project_name}_{voice_name}", 0)
            usage_pairs.append((usage, voice_name))

        # Ưu tiên tuyệt đối theo usage tăng dần.
        # Với các voice cùng usage thì đảo ngẫu nhiên để tránh lặp thứ tự cứng.
        usage_groups = {}
        for usage, voice_name in usage_pairs:
            usage_groups.setdefault(usage, []).append(voice_name)

        ordered_voices = []
        for usage in sorted(usage_groups.keys()):
            same_usage = usage_groups[usage]
            random.shuffle(same_usage)
            ordered_voices.extend(same_usage)

        picked = ordered_voices[:picks_needed]
        for chosen_voice in picked:
            key = f"{project_name}_{chosen_voice}"
            voice_usage_db[key] = voice_usage_db.get(key, 0) + 1

        return picked

    def reserve_render_queue_voices(self, render_queue):
        """Giữ chỗ voice ngay khi gom queue để batch chờ sau không bốc trùng."""
        if not render_queue:
            return
        try:
            import database
            with database.db_lock:
                conn = database.get_connection()
                cursor = conn.cursor()
                for voice_name, _proj_dir, proj_name in render_queue:
                    project_id = database.get_or_create_project(proj_name)
                    cursor.execute(
                        """
                        UPDATE voices
                        SET last_used = datetime('now', 'localtime')
                        WHERE project_id = ? AND file_name = ?
                        """,
                        (project_id, voice_name),
                    )
                conn.commit()
                conn.close()
        except Exception as exc:
            print(f"⚠️ Không giữ chỗ voice bot được: {exc}")

    def create_render_jobs_for_queue(self, batch_id, chat_id, render_queue, label):
        try:
            import database
            return database.create_render_jobs(batch_id, self.get_active_profile_name(), chat_id, label, render_queue)
        except Exception as exc:
            print(f"⚠️ Không tạo render_jobs được: {exc}")
            self.reserve_render_queue_voices(render_queue)
            return [None] * len(render_queue)

    def _get_safe_render_threads(self):
        try:
            return max(1, int(self.main_app.config.get("threads", 2)))
        except (TypeError, ValueError):
            return 2

    def _build_bot_render_config(self):
        config = dict(self.main_app.config)
        profile_name = self.get_active_profile_name()
        profile_cover = config.get("profile_enable_cover", {})
        if isinstance(profile_cover, dict) and profile_name in profile_cover:
            config["enable_cover"] = bool(profile_cover[profile_name])
        else:
            config["enable_cover"] = bool(config.get("enable_cover", True))
        return config

    def _ask_schedule_then_start_render(self, chat_id, render_queue, done_label, cleanup=None):
        if not render_queue:
            self.bot.send_message(chat_id, "❌ Không có video nào trong hàng chờ render.")
            if cleanup:
                cleanup()
            return

        sent_msg = self.bot.send_message(
            chat_id,
            "⏰ Render xong có tự chia lịch đăng TikTok không?\n"
            "Trả lời: co / khong\n"
            "Nếu chọn co, em sẽ lấy giờ hiện tại, chia các mốc tăng dần và mỗi mốc đăng 1 video để tránh dồn bài."
        )

        def process_schedule_choice(message):
            text = (message.text or "").strip().lower()
            auto_schedule = text in ("co", "có", "yes", "y", "ok", "oke", "1")
            if cleanup:
                cleanup()
            if auto_schedule:
                self.bot.send_message(chat_id, "✅ Đã chọn tự chia lịch sau render.")
            else:
                self.bot.send_message(chat_id, "✅ Không đặt lịch sau render, chỉ render video.")
            threading.Thread(target=self._run_bot_render_queue, args=(chat_id, render_queue, done_label, auto_schedule), daemon=True).start()

        self.bot.register_next_step_handler(sent_msg, process_schedule_choice)

    def _run_bot_render_queue(self, chat_id, render_queue, done_label, auto_schedule=False):
        if not render_queue:
            self.bot.send_message(chat_id, "❌ Không có video nào trong hàng chờ render.")
            return

        batch_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
        batch_info = {
            "id": batch_id,
            "label": done_label,
            "total": len(render_queue),
            "completed": 0,
            "chat_id": chat_id,
            "queued_at": time.time(),
            "started_at": None,
        }

        if self.render_batch_lock.locked():
            with self.render_status_lock:
                self.waiting_render_batches.append(batch_info)
            self.bot.send_message(chat_id, "⏳ Máy đang render batch khác. Em đã đưa lệnh này vào hàng chờ, xong batch trước sẽ chạy tiếp.")

        with self.render_batch_lock:
            try:
                job_ids = self.create_render_jobs_for_queue(batch_id, chat_id, render_queue, done_label)
                with self.render_status_lock:
                    self.waiting_render_batches = [b for b in self.waiting_render_batches if b.get("id") != batch_id]
                    batch_info["started_at"] = time.time()
                    self.current_render_batch = batch_info

                completed = 0
                batch_config = self._build_bot_render_config()
                max_workers = self._get_safe_render_threads()
                self.main_app.tab2.completed_count = 0
                with self.main_app.tab2.opening_lock:
                    self.main_app.tab2.used_opening_videos.clear()
                with self.main_app.tab2.broll_lock:
                    self.main_app.tab2.used_broll_videos.clear()

                self.bot.send_message(chat_id, f"🧵 Bắt đầu render {len(render_queue)} video với {max_workers} luồng ổn định.")
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}
                    for job_id, (voice_name, proj_dir, proj_name) in zip(job_ids, render_queue):
                        future = executor.submit(self._render_one_with_retry, voice_name, proj_dir, proj_name, batch_config, job_id)
                        futures[future] = (job_id, voice_name)
                        time.sleep(1.5)

                    for future in concurrent.futures.as_completed(futures):
                        job_id, voice_name = futures[future]
                        try:
                            result = future.result()
                            if result:
                                completed += 1
                                if job_id:
                                    import database
                                    database.update_render_job(job_id, "done")
                            elif job_id:
                                import database
                                database.update_render_job(job_id, "failed", error=f"Render trả về False: {voice_name}")
                        except Exception as exc:
                            if job_id:
                                try:
                                    import database
                                    database.update_render_job(job_id, "failed", error=exc)
                                except Exception:
                                    pass
                            print(f"⚠️ Lỗi render bot: {exc}")
                        with self.render_status_lock:
                            if self.current_render_batch and self.current_render_batch.get("id") == batch_id:
                                self.current_render_batch["completed"] = completed

                self.bot.send_message(chat_id, f"🎉 DẠ XONG! {done_label} đã xuất xưởng {completed}/{len(render_queue)} video.\nSếp gõ /icloud để nhận hàng nhé!")
                if completed > 0 and auto_schedule and hasattr(self.main_app, "tab13"):
                    try:
                        self.main_app.root.after(0, lambda: self.main_app.tab13.create_incremental_schedule_after_render("bot"))
                        self.bot.send_message(chat_id, "⏰ Render xong em đã chia lịch đăng tăng dần cho toàn bộ video đang chờ ở tab 13.")
                    except Exception as e:
                        print(f"⚠️ Không tự lên lịch tab 13 sau render bot được: {e}")
                try:
                    self.main_app.tab4.load_excel_data()
                except Exception as e:
                    print(f"⚠️ Lỗi load_excel_data: {e}")
            finally:
                with self.render_status_lock:
                    if self.current_render_batch and self.current_render_batch.get("id") == batch_id:
                        self.current_render_batch = None

    def get_render_status_text(self):
        try:
            import database
            recent_jobs = database.list_recent_render_jobs(12, self.get_active_profile_name())
        except Exception:
            recent_jobs = []

        with self.render_status_lock:
            current = dict(self.current_render_batch) if self.current_render_batch else None
            waiting = [dict(item) for item in self.waiting_render_batches]

        if not current and not waiting:
            return "✅ Hiện không có batch render nào đang chạy hoặc đang chờ."

        lines = ["📊 TRẠNG THÁI RENDER BOT"]
        now = time.time()
        if current:
            elapsed_min = int((now - (current.get("started_at") or now)) / 60)
            lines.append(f"Đang chạy: {current.get('label')} - {current.get('completed', 0)}/{current.get('total', 0)} video - {elapsed_min} phút")
        else:
            lines.append("Đang chạy: không có")

        if waiting:
            lines.append(f"Đang chờ: {len(waiting)} batch")
            for idx, item in enumerate(waiting[:5], 1):
                wait_min = int((now - (item.get("queued_at") or now)) / 60)
                lines.append(f"{idx}. {item.get('label')} - {item.get('total', 0)} video - chờ {wait_min} phút")
        else:
            lines.append("Đang chờ: 0 batch")

        if recent_jobs:
            lines.append("Job gần nhất:")
            icon_map = {"queued": "⏳", "running": "🧵", "done": "✅", "failed": "❌", "cancelled": "🚫"}
            for job in recent_jobs[:8]:
                icon = icon_map.get(job["status"], "•")
                lines.append(f"{icon} #{job['id']} {job['project_name']} | {job['voice_name']} | {job['status']}")

        return "\n".join(lines)

    def _render_one_with_retry(self, voice_name, proj_dir, proj_name, batch_config, job_id=None, max_attempts=2):
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                if job_id:
                    import database
                    database.update_render_job(job_id, "running")
                result = self.main_app.tab2._process_single(voice_name, proj_dir, proj_name, batch_config)
                if result:
                    return True
                last_error = "Render trả về False"
            except Exception as exc:
                last_error = exc

            if attempt < max_attempts:
                try:
                    self.main_app.tab2.add_log(f"[{voice_name}] 🔁 Render lỗi, thử lại lần {attempt + 1}/{max_attempts}...")
                except Exception:
                    pass
                time.sleep(3)

        if last_error:
            raise Exception(last_error)
        return False
    

    def start_telegram_bot(self):
        if self.bot_is_running:
            print("⚠️ Bot đang chạy rồi, từ chối khởi động đúp!")
            return

        token = self.main_app.config.get("telegram_bot_token", "")
        if not token:
            print("⚠️ Chưa có Token Telegram, Bot đang ngủ.")
            return

        self.bot = telebot.TeleBot(token)
        self.bot_sessions = {} 

        # =======================================================
        # 1. LỆNH: SÁCH HƯỚNG DẪN (/help hoặc /start)
        # =======================================================
        @self.bot.message_handler(commands=['help', 'start'])
        def send_help_menu(message):
            self.register_notify_chat(message.chat.id)
            current_profile = self.get_active_profile_name()
            help_text = (
                "🤖 *TRỢ LÝ ĐẠO DIỄN AI KÍNH CHÀO SẾP!* 🎬\n\n"
                f"🏛️ Tài khoản đang điều khiển: *{current_profile}*\n\n"
                "Sếp cần em giúp gì nào? Đây là các lệnh để điều khiển dàn máy ở nhà:\n\n"
                "📁 /projects - Xem danh sách và bật/tắt Project.\n"
                "🏛️ /account - Đổi tài khoản làm việc ngay trên bot.\n"
                "✏️ /renameaccount - Đổi tên tài khoản hiện tại.\n"
                "🚀 /menu (hoặc /render) - Chọn 1 dự án để lên đơn làm video.\n"
                "📚 /multimenu - Chọn NHIỀU dự án cùng lúc để bốc Voice tự động.\n"
                "🎲 /autobatch - Bốc random TẤT CẢ dự án mỗi nơi vài Voice.\n"
                "📦 /files - Vào kho xem video & trạng thái.\n"
                "🌐 /dang [số lượng] - Chạy Tab 13 đăng TikTok/Web.\n"
                "☁️ /icloud - Đồng bộ toàn bộ hàng mới sang iCloud.\n"
                "🧹 /clean - Dọn dẹp video cũ trên iCloud.\n"
                "🌐 /web - Bật/Tắt Trạm phát sóng LAN để tải video.\n"
                "💡 *Mẹo nhỏ:* Ở lệnh /projects, sếp cứ gõ số thứ tự (1, 2, 3...) là cúp điện (đóng băng) hoặc mở khóa project ngay lập tức, không cần gõ chữ đâu nha!"
            )
            self.bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

        # =======================================================
        # 2. LỆNH: MENU TƯƠNG TÁC ĐÓNG BĂNG PROJECT BẰNG SỐ
        # =======================================================
        @self.bot.message_handler(commands=['projects', 'toggle'])
        def list_and_toggle_projects(message):
            self.register_notify_chat(message.chat.id)
            if not self.main_app.projects:
                return self.bot.send_message(message.chat.id, "❌ Kho chưa có Project nào!")

            current_profile = self.get_active_profile_name()
            sorted_projects = sorted(self.main_app.projects.items(), key=lambda x: x[1]['created_at'], reverse=True)
            msg = f"📁 DANH SÁCH PROJECT - TK {current_profile}:\n\n"
            for idx, (pid, pdata) in enumerate(sorted_projects, 1):
                status = "🟢 Đang mở" if pdata.get('status', 'active') == 'active' else "🔴 Đã Đóng Băng"
                msg += f"{idx}. {pdata['name']} [{status}]\n"

            msg += "\n👉 Nhập MỘT SỐ THỨ TỰ (VD: 1, 2 hoặc 3) để Đóng/Mở băng. (Nhập chữ bất kỳ để hủy)"
            sent_msg = self.bot.send_message(message.chat.id, msg)
            self.bot.register_next_step_handler(sent_msg, process_toggle_step, sorted_projects, current_profile)

        @self.bot.message_handler(commands=['account', 'accounts', 'profile', 'taikhoan'])
        def handle_account_switch(message):
            self.register_notify_chat(message.chat.id)
            chat_id = message.chat.id
            profiles = self.get_available_profiles()
            current_profile = self.get_active_profile_name()

            if not profiles:
                return self.bot.send_message(chat_id, "❌ Chưa có tài khoản nào để đổi sếp ơi.")

            msg = f"🏛️ TÀI KHOẢN HIỆN TẠI: {current_profile}\n\n"
            msg += "Danh sách tài khoản đang có:\n"
            for idx, name in enumerate(profiles, 1):
                icon = "✅" if name == current_profile else "▫️"
                msg += f"{idx}. {icon} {name}\n"
            msg += "\n👉 Sếp nhắn số thứ tự hoặc gõ đúng tên tài khoản để đổi nhé."

            with self.session_lock:
                self.bot_sessions[chat_id] = {'profile_options': profiles}

            sent_msg = self.bot.send_message(chat_id, msg)
            self.bot.register_next_step_handler(sent_msg, process_account_switch)

        def process_account_switch(message):
            chat_id = message.chat.id
            text = message.text.strip()
            with self.session_lock:
                session = self.bot_sessions.get(chat_id)

            if not session or 'profile_options' not in session:
                return self.bot.send_message(chat_id, "❌ Phiên chọn tài khoản đã hết hạn, sếp gõ lại lệnh giúp em nhé.")

            profiles = session.get('profile_options', [])
            target_profile = None

            if text.isdigit():
                idx = int(text) - 1
                if 0 <= idx < len(profiles):
                    target_profile = profiles[idx]
            else:
                for name in profiles:
                    if name.casefold() == text.casefold():
                        target_profile = name
                        break

            with self.session_lock:
                self.bot_sessions.pop(chat_id, None)

            if not target_profile:
                return self.bot.send_message(chat_id, "❌ Em không thấy tài khoản đó. Bác gõ lại lệnh rồi chọn lại giúp em nhé.")

            self.bot.send_message(chat_id, f"⏳ Đang chuyển sang tài khoản {target_profile}...")
            self.switch_profile_from_bot(chat_id, target_profile)

        @self.bot.message_handler(commands=['renameaccount', 'renameprofile', 'doiten'])
        def handle_account_rename(message):
            chat_id = message.chat.id
            current_profile = self.get_active_profile_name()
            sent_msg = self.bot.send_message(chat_id, f"✏️ Tài khoản hiện tại là: {current_profile}\n\n👉 Sếp nhắn tên mới để em đổi ngay nhé.")
            self.bot.register_next_step_handler(sent_msg, process_account_rename, current_profile)

        def process_account_rename(message, old_profile):
            chat_id = message.chat.id
            new_profile_name = message.text.strip()
            if not new_profile_name:
                return self.bot.send_message(chat_id, "❌ Tên mới đang bị trống, sếp gõ lại giúp em nhé.")
            self.bot.send_message(chat_id, f"⏳ Đang đổi tên tài khoản {old_profile}...")
            self.rename_profile_from_bot(chat_id, old_profile, new_profile_name)

        @self.bot.message_handler(commands=['web', 'server'])
        def handle_web_server(message):
            self.register_notify_chat(message.chat.id)
            chat_id = message.chat.id
            is_currently_on = hasattr(self.main_app.tab4, 'httpd') and self.main_app.tab4.httpd is not None
            
            if is_currently_on:
                self.bot.send_message(chat_id, "⏳ Sếp đợi em xíu, em đang sập cầu dao Trạm phát sóng...")
            else:
                self.bot.send_message(chat_id, "⏳ Sếp đợi em xíu, em đang dọn kho và bật Trạm phát sóng...")
                
            self.main_app.root.after(0, lambda: self.main_app.tab4.toggle_web_server(bot=self.bot, chat_id=chat_id))

        def process_toggle_step(message, sorted_projects, profile_name):
            text = message.text.strip()
            if not text.isdigit():
                return self.bot.send_message(message.chat.id, "✅ Đã hủy thao tác.")

            idx = int(text) - 1 
            if idx < 0 or idx >= len(sorted_projects):
                return self.bot.send_message(message.chat.id, "❌ Số không hợp lệ. Đã hủy thao tác.")

            target_pid, pdata = sorted_projects[idx]
            current = pdata.get('status', 'active')
            new_status = 'disabled' if current == 'active' else 'active'

            if profile_name == self.get_active_profile_name():
                if target_pid in self.main_app.projects:
                    self.main_app.projects[target_pid]['status'] = new_status
                    self.main_app.save_projects()
                    self.main_app.root.after(0, self.main_app.tab1.refresh_project_list)
                    self.main_app.root.after(0, self.main_app.tab2.update_combo_projects)
            else:
                projects_data = self.main_app.load_projects_for_profile(profile_name)
                if target_pid in projects_data:
                    projects_data[target_pid]['status'] = new_status
                    self.main_app.save_projects_for_profile(profile_name, projects_data)

            state_str = "🟢 ĐÃ MỞ KHÓA" if new_status == 'active' else "🔴 ĐÃ ĐÓNG BĂNG"
            self.bot.send_message(message.chat.id, f"✅ {state_str} project trong tài khoản {profile_name}:\n👉 {pdata['name']}")


        # =======================================================
        # CÁC LỆNH KHÁC CỦA SẾP
        # =======================================================
        @self.bot.message_handler(commands=['renderstatus', 'queue', 'statusrender'])
        def handle_render_status(message):
            self.register_notify_chat(message.chat.id)
            self.bot.send_message(message.chat.id, self.get_render_status_text())

        @self.bot.message_handler(commands=['dang', 'post', 'autopost', 'webpost'])
        def handle_web_post(message):
            self.register_notify_chat(message.chat.id)
            chat_id = message.chat.id
            parts = (message.text or "").split()
            count = 1
            if len(parts) >= 2:
                try:
                    count = max(1, min(100, int(parts[1])))
                except Exception:
                    return self.bot.send_message(chat_id, "❌ Cú pháp: /dang hoặc /dang 5")

            if not hasattr(self.main_app, "tab13"):
                return self.bot.send_message(chat_id, "❌ Tool chưa có Tab 13 để đăng web.")
            if self.main_app.tab13.is_running:
                return self.bot.send_message(chat_id, "⏳ Tab 13 đang chạy job khác, sếp chờ xong rồi gọi lại nhé.")

            self.bot.send_message(chat_id, f"🌐 Đã nhận lệnh đăng {count} video bằng Tab 13. Xong video nào em báo video đó.")
            self.main_app.root.after(0, lambda c=count: self.main_app.tab13.start_scheduled_post(c))

        @self.bot.message_handler(commands=['cancelqueue', 'huyqueue'])
        def handle_cancel_queue(message):
            with self.render_status_lock:
                waiting_count = len(self.waiting_render_batches)
                self.waiting_render_batches.clear()
            try:
                import database
                db_count = database.cancel_queued_render_jobs(self.get_active_profile_name())
            except Exception:
                db_count = 0
            self.bot.send_message(message.chat.id, f"🚫 Đã hủy {waiting_count} batch chờ trong bộ nhớ và {db_count} job queued trong DB. Batch đang chạy vẫn để chạy xong cho an toàn.")

        @self.bot.message_handler(commands=['files', 'kho'])
        def handle_view_files(message):
            chat_id = message.chat.id
            self.bot.send_chat_action(chat_id, 'typing')
            output_dir = self.get_live_output_dir()
            current_profile = self.get_active_profile_name()
            if not os.path.exists(output_dir): return self.bot.send_message(chat_id, "❌ Em không tìm thấy thư mục kho hàng!")

            video_files = [f for f in os.listdir(output_dir) if f.lower().endswith('.mp4')]
            if not video_files: return self.bot.send_message(chat_id, f"🏜️ Kho hàng của tài khoản {current_profile} đang trống trơn sếp ạ!")

            video_files.sort(key=lambda x: os.path.getmtime(os.path.join(output_dir, x)), reverse=True)
            _, _, _, _, raw_lines = self.get_bot_stats()
            
            msg = f"📊 **KHO THÀNH PHẨM - {current_profile} ({len(video_files)} video):**\n\n"
            file_map = []
            
            for i, f_name in enumerate(video_files[:15], 1): 
                file_map.append(f_name)
                tail_code = f_name[-12:] if len(f_name) > 12 else f_name
                stt = "Chưa rõ"
                for line in reversed(raw_lines):
                    if tail_code in line:
                        if "Đã chuyển" in line: stt = "Đã chuyển"
                        elif "Chưa chuyển" in line: stt = "Chưa chuyển"
                        break
                        
                icon = "🟢" if "Đã" in stt else "🟡"
                msg += f"{i}. {icon} `{f_name}` *(Trạng thái: {stt})*\n"

            msg += "\n👉 Sếp muốn ném file nào vào iCloud thì **nhắn lại các số thứ tự (cách nhau bằng dấu phẩy)** nhé (VD: 1,3,5)!"
            with self.session_lock:
                self.bot_sessions[chat_id] = {'file_map': file_map, 'output_dir': output_dir, 'profile_name': current_profile}
            msg_sent = self.bot.send_message(chat_id, msg, parse_mode="Markdown")
            self.bot.register_next_step_handler(msg_sent, process_file_delivery)

        def process_file_delivery(message):
            chat_id = message.chat.id
            text = message.text.strip()
            with self.session_lock:
                session = self.bot_sessions.get(chat_id)
            if not session or 'file_map' not in session: return

            try:
                choices = [int(x.strip()) - 1 for x in text.split(',')]
                # ✅ Bounds check - tránh IndexError
                if any(i < 0 or i >= len(session['file_map']) for i in choices):
                    return self.bot.send_message(chat_id, "❌ Số không hợp lệ sếp ơi!")
                target_files = [session['file_map'][i] for i in choices]
            except ValueError:
                return self.bot.send_message(chat_id, "❌ Sếp gõ sai cú pháp rồi (VD chuẩn: 1,3,5)!")
            except Exception as e:
                print(f"⚠️ Lỗi process_file_delivery: {e}")
                return self.bot.send_message(chat_id, f"❌ Lỗi: {str(e)[:50]}")

            self.bot.send_message(chat_id, f"🚀 Đang gom {len(target_files)} file ném thẳng vào iCloud Drive...")
            self.bot.send_chat_action(chat_id, 'upload_document')
            
            try:
                icloud_dir = self.main_app.config.get("icloud_path", "")
                folder_name = f"Auto_iCloud_{datetime.now().strftime('%d%m%Y_%H%M')}"
                target_dir = os.path.join(icloud_dir, folder_name)
                os.makedirs(target_dir, exist_ok=True)
                
                success_count = 0
                output_dir = session.get('output_dir', self.get_live_output_dir())
                for target_file in target_files:
                    file_path = os.path.join(output_dir, target_file)
                    if os.path.exists(file_path):
                        target_path = os.path.join(target_dir, f"[{datetime.now().strftime('%Y%m%d_%H%M')}]_{target_file}")
                        shutil.copy2(file_path, target_path)
                        
                        try: self.main_app.tab4.update_excel_status(file_path, "Đã chuyển")
                        except: pass
                        success_count += 1
                
                try: self.main_app.tab4.load_excel_data()
                except: pass
                
                self.bot.send_message(chat_id, f"✅ **Xong rồi sếp ơi!** Đã đẩy thành công {success_count}/{len(target_files)} file vào iCloud mục `{folder_name}`.")
            except Exception as e:
                print(f"⚠️ Lỗi process_file_delivery copy: {e}")
                self.bot.send_message(chat_id, f"❌ Lỗi copy vào iCloud: {str(e)[:50]}")
            finally:
                # 🧹 Cleanup session
                with self.session_lock:
                    self.bot_sessions.pop(chat_id, None)

        @self.bot.message_handler(commands=['autobatch', 'random'])
        def handle_auto_batch(message):
            chat_id = message.chat.id
            self.bot.send_message(chat_id, "🎲 Dạ sếp! Em đang soi sổ Excel để bốc ưu tiên các Voice ÍT DÙNG NHẤT đây...")
            
            voice_usage_db = self.get_voice_usage()
            render_queue = [] 
            profile_name = self.get_active_profile_name()
            projects = self.main_app.load_projects_for_profile(profile_name)
            
            for pid, pdata in projects.items():
                if str(pdata.get("status", "active")) != "active":
                    continue
                pname = pdata.get('name', 'Unknown')
                pdir = self.main_app.get_proj_dir(pid, profile_name)
                vdir = os.path.join(pdir, "Voices")
                
                if os.path.exists(vdir):
                    voices = [f for f in os.listdir(vdir) if f.lower().endswith(VOICE_FILE_EXTS)]
                    if voices:
                        num_to_pick = min(2, len(voices))
                        for chosen_voice in self.pick_least_used_voices(pname, voices, voice_usage_db, num_to_pick):
                            render_queue.append((chosen_voice, pdir, pname))

            if not render_queue: return self.bot.send_message(chat_id, "❌ Kho voice nhà mình trống trơn chưa có file nào sếp ơi!")
            self.bot.send_message(chat_id, f"🚀 ĐÃ GOM ĐƯỢC {len(render_queue)} BÀI (Ưu tiên Voice mới/Random)!\nEm tống hết vào máy nổ luồng luôn nha sếp. 🏃‍♀️💨")

            self._ask_schedule_then_start_render(chat_id, render_queue, "Chuyến xe Random")

        @self.bot.message_handler(commands=['multimenu', 'chonnhieu'])
        def handle_multi_menu(message):
            chat_id = message.chat.id
            if not self.main_app.projects: return self.bot.send_message(chat_id, "❌ Kho trống trơn sếp ơi!")
            
            current_profile = self.get_active_profile_name()
            proj_list = [(pid, p.get('name'), p.get('status', 'active')) for pid, p in self.main_app.projects.items()]
            msg = f"📁 **CHỌN NHIỀU DỰ ÁN ĐỂ CHẠY TỰ ĐỘNG - {current_profile}:**\n\n"
            for i, (p, n, st) in enumerate(proj_list, 1):
                status_text = "🟢" if str(st) == "active" else "🔴"
                msg += f" {i}. {status_text} {n}\n"
            msg += "\n👇 Sếp nhắn **các số thứ tự** cách nhau bằng dấu phẩy nhé (VD: 1,3,5):"
            
            with self.session_lock:
                self.bot_sessions[chat_id] = {'proj_list': proj_list, 'profile_name': current_profile}
            msg_sent = self.bot.send_message(chat_id, msg, parse_mode="Markdown")
            self.bot.register_next_step_handler(msg_sent, process_multi_project_choice)

        def process_multi_project_choice(message):
            chat_id = message.chat.id
            text = message.text.strip()
            with self.session_lock:
                sess = self.bot_sessions.get(chat_id)
            if not sess or 'proj_list' not in sess: return

            try:
                choices = [int(x.strip()) - 1 for x in text.split(',')]
                # ✅ Bounds check - tránh IndexError
                if any(i < 0 or i >= len(sess['proj_list']) for i in choices):
                    return self.bot.send_message(chat_id, "❌ Số không hợp lệ sếp ơi!")
                selected_projects = [sess['proj_list'][i] for i in choices]
            except ValueError:
                return self.bot.send_message(chat_id, "❌ Sếp gõ sai cú pháp rồi (VD chuẩn: 1,3,5)!")
            except Exception as e:
                print(f"⚠️ Lỗi process_multi_project_choice: {e}")
                return self.bot.send_message(chat_id, f"❌ Lỗi: {str(e)[:50]}")

            voice_usage_db = self.get_voice_usage()
            render_queue = []
            msg_log = "🎲 **Báo cáo kết quả đi chợ (Ưu tiên Voice ít dùng):**\n"

            profile_name = sess.get('profile_name', self.get_active_profile_name())
            for pid, proj_name, proj_status in selected_projects:
                if str(proj_status) != "active":
                    msg_log += f"⛔ `{proj_name}`: Đang đóng băng, bỏ qua!\n"
                    continue
                pdir = self.main_app.get_proj_dir(pid, profile_name)
                vdir = os.path.join(pdir, "Voices")
                if os.path.exists(vdir):
                    voices = [f for f in os.listdir(vdir) if f.lower().endswith(VOICE_FILE_EXTS)]
                    if voices:
                        num_to_pick = min(random.randint(2, 3), len(voices))
                        picked_count = 0
                        
                        for chosen_voice in self.pick_least_used_voices(proj_name, voices, voice_usage_db, num_to_pick):
                            render_queue.append((chosen_voice, pdir, proj_name))
                            picked_count += 1
                            
                        msg_log += f"✅ `{proj_name}`: Đã ép nổ {picked_count} video.\n"
                    else:
                        msg_log += f"⚠️ `{proj_name}`: Thư mục chưa copy âm thanh, bỏ qua!\n"
                else:
                    msg_log += f"⚠️ `{proj_name}`: Không có thư mục Voices, bỏ qua!\n"

            if not render_queue:
                return self.bot.send_message(chat_id, msg_log + "\n❌ Túm lại là không bốc được cái voice nào sếp ạ!")

            self.bot.send_message(chat_id, msg_log + f"\n🚀 **TỔNG CỘNG ĐÃ GOM {len(render_queue)} BÀI!**\nEm tống hết vào máy nổ luồng luôn nha sếp! 🏃‍♀️💨", parse_mode="Markdown")

            with self.session_lock:
                self.bot_sessions.pop(chat_id, None)
            self._ask_schedule_then_start_render(chat_id, render_queue, "Chuyến xe Multi-Project")
            
        # --- BẮT TỪ KHÓA ---
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['dọn dẹp', 'xóa rác']))
        def natural_clean(message): handle_clean_icloud(message)
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['làm video', 'lên đơn', 'menu']))
        def natural_menu(message): handle_menu(message)
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['vào kho', 'lấy file', 'trạng thái']))
        def natural_files(message): handle_view_files(message)
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['đồng bộ', 'đẩy lên', 'sync']))
        def natural_icloud(message): handle_sync_icloud(message)
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['đổi tài khoản', 'chuyển tài khoản', 'đổi profile']))
        def natural_account(message): handle_account_switch(message)
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['đổi tên tài khoản', 'sửa tên tài khoản', 'đổi tên profile']))
        def natural_rename_account(message): handle_account_rename(message)
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['chạy random', 'bốc ngẫu nhiên', 'chạy tự động']))
        def natural_autobatch(message): handle_auto_batch(message)
        @self.bot.message_handler(func=lambda message: not message.text.startswith('/') and any(kw in message.text.lower() for kw in ['chạy nhiều', 'chọn nhiều', 'chạy lô']))
        def natural_multimenu(message): handle_multi_menu(message)

        @self.bot.message_handler(commands=['clean', 'dondep'])
        def handle_clean_icloud(message):
            chat_id = message.chat.id
            icloud_dir = self.main_app.config.get("icloud_path", "")
            if not icloud_dir: 
                return self.bot.send_message(chat_id, "❌ Em chưa thấy thư mục iCloud ở nhà.")
                
            folders_to_delete = [os.path.join(icloud_dir, item) for item in os.listdir(icloud_dir) if (item.startswith("Video_Xuat") or item.startswith("Auto_iCloud")) and os.path.isdir(os.path.join(icloud_dir, item))]
            
            if not folders_to_delete: 
                return self.bot.send_message(chat_id, "✨ iCloud nhà mình đang sạch bong sếp ơi!")
                
            with self.session_lock:
                self.bot_sessions[chat_id] = {'folders_to_delete': folders_to_delete}
            msg_sent = self.bot.send_message(chat_id, f"🧹 TÌM THẤY {len(folders_to_delete)} LÔ HÀNG CŨ!\nSếp nhắn chữ: **XOA** để em phi tang nhé.")
            
            def confirm_clean(m):
                if m.text.strip().upper() == "XOA":
                    deleted = 0
                    for f in folders_to_delete:
                        try:
                            shutil.rmtree(f)
                            deleted += 1
                        except: pass
                    self.bot.send_message(chat_id, f"Đã dọn dẹp xong {deleted} thư mục rác! 🗑️")
                else:
                    self.bot.send_message(chat_id, "Đã hủy dọn dẹp, hàng họ vẫn còn nguyên sếp nhé!")
                # 🧹 Cleanup session
                with self.session_lock:
                    self.bot_sessions.pop(chat_id, None)
                    
            self.bot.register_next_step_handler(msg_sent, confirm_clean)

        @self.bot.message_handler(commands=['menu', 'render'])
        def handle_menu(message):
            chat_id = message.chat.id
            if not self.main_app.projects: return self.bot.send_message(chat_id, "Kho trống trơn sếp ơi!")
            current_profile = self.get_active_profile_name()
            proj_list = [(pid, p.get('name'), p.get('status', 'active')) for pid, p in self.main_app.projects.items()]
            msg_lines = []
            for i, (p, n, st) in enumerate(proj_list, 1):
                status_text = "🟢" if str(st) == "active" else "🔴"
                msg_lines.append(f" {i}. {status_text} {n}")
            msg = f"📁 **Dự án nhà mình - {current_profile}:**\n" + "\n".join(msg_lines) + "\n\n👇 Sếp nhắn **số thứ tự** Project nhé:"
            with self.session_lock:
                self.bot_sessions[chat_id] = {'proj_list': proj_list, 'profile_name': current_profile}
            self.bot.register_next_step_handler(self.bot.send_message(chat_id, msg, parse_mode="Markdown"), process_project_choice)

        def process_project_choice(message):
            chat_id = message.chat.id
            try:
                with self.session_lock:
                    sess = self.bot_sessions.get(chat_id)
                if not sess or 'proj_list' not in sess:
                    return self.bot.send_message(chat_id, "❌ Session hết hạn, gõ lại lệnh /menu nhé!")
                idx = int(message.text.strip()) - 1
                if idx < 0 or idx >= len(sess['proj_list']):
                    return self.bot.send_message(chat_id, "❌ Số không hợp lệ sếp ơi!")
                pid, proj_name, proj_status = sess['proj_list'][idx]
            except ValueError:
                return self.bot.send_message(chat_id, "Sếp gõ sai số rồi!")
            except Exception as e:
                print(f"⚠️ Lỗi process_project_choice: {e}")
                return self.bot.send_message(chat_id, f"❌ Lỗi: {str(e)[:50]}")

            if str(proj_status) != "active":
                return self.bot.send_message(chat_id, f"⛔ Project `{proj_name}` đang đóng băng, mở lại rồi hãy render nhé.")
            
            profile_name = sess.get('profile_name', self.get_active_profile_name())
            pdir = self.main_app.get_proj_dir(pid, profile_name); vdir = os.path.join(pdir, "Voices")
            voices = [f for f in os.listdir(vdir) if f.lower().endswith(VOICE_FILE_EXTS)] if os.path.exists(vdir) else []
            if not voices: return self.bot.send_message(chat_id, f"Không có voice nào trong {proj_name}!")
            
            with self.session_lock:
                self.bot_sessions[chat_id].update({'pid': pid, 'proj_name': proj_name, 'voice_map': voices, 'proj_dir': pdir})
            
            # --- CẬP NHẬT: HIỆN DANH SÁCH VOICE RÕ RÀNG ---
            msg = f"🎧 **Dự án `{proj_name}` đang có {len(voices)} file âm thanh:**\n\n"
            for i, v in enumerate(voices, 1):
                msg += f" {i}. `{v}`\n"
            msg += "\n👇 Sếp chốt số mấy? (Nhắn các số cách nhau bằng dấu phẩy VD: 1,3)"
            self.bot.register_next_step_handler(self.bot.send_message(chat_id, msg, parse_mode="Markdown"), process_voice_choice)

        def process_voice_choice(message):
            chat_id = message.chat.id
            with self.session_lock:
                sess = self.bot_sessions.get(chat_id)
            if not sess or 'voice_map' not in sess:
                return self.bot.send_message(chat_id, "❌ Session hết hạn, gõ lại lệnh /menu nhé!")
            try:
                choices = [int(x.strip()) - 1 for x in message.text.split(',')]
                # ✅ Bounds check - tránh IndexError
                if any(i < 0 or i >= len(sess['voice_map']) for i in choices):
                    return self.bot.send_message(chat_id, "❌ Số không hợp lệ sếp ơi!")
                selected = [sess['voice_map'][i] for i in choices]
            except ValueError:
                return self.bot.send_message(chat_id, "Sai cú pháp!")
            except Exception as e:
                print(f"⚠️ Lỗi process_voice_choice: {e}")
                return self.bot.send_message(chat_id, f"❌ Lỗi: {str(e)[:50]}")
            
            self.bot.send_message(chat_id, f"🚀 Bắt đầu xào nấu {len(selected)} video!")
            
            # --- CẬP NHẬT: ĐA LUỒNG CÓ THẢ CỬA NGẮT QUÃNG 1.5 GIÂY ---
            render_queue = [(v, sess['proj_dir'], sess['proj_name']) for v in selected]
            def cleanup_menu_session():
                with self.session_lock:
                    self.bot_sessions.pop(chat_id, None)

            self._ask_schedule_then_start_render(
                chat_id,
                render_queue,
                "Đơn của sếp",
                cleanup=cleanup_menu_session,
            )

        @self.bot.message_handler(commands=['icloud', 'sync'])
        def handle_sync_icloud(message):
            self.bot.reply_to(message, "Dạ rõ! Đang ném vào iCloud cho sếp... 📦💨")
            threading.Thread(target=self.main_app.tab4.auto_sync_icloud, args=(self.bot, message.chat.id), daemon=True).start()

        @self.bot.message_handler(func=lambda message: not message.text.startswith('/'))
        def handle_free_chat(message):
            chat_id = message.chat.id
            user_text = message.text
            groq_key = self.main_app.config.get("groq_key", "").strip()
            if not groq_key: return self.bot.reply_to(message, "Sếp ơi chưa có Key Llama 3.3 ở Tab 2!")
            self.bot.send_chat_action(chat_id, 'typing')
            
            total_vids, today_vids, da_chuyen, chua_chuyen, _ = self.get_bot_stats()

            def fetch_ai_reply():
                try:
                    url = "https://api.groq.com/openai/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                    
                    sys_prompt = (
                        f"Bạn là nữ thư ký AI 'Trợ Lý Video' quản lý xưởng edit. Xưng em, gọi sếp. "
                        f"Báo cáo kho hiện tại: Tổng đã SX {total_vids} video (Riêng hôm nay làm được: {today_vids}). "
                        f"TÌNH TRẠNG KHO: Đã đẩy lên iCloud {da_chuyen} video. CÒN TỒN TRONG MÁY {chua_chuyen} video (Chưa chuyển). "
                        f"Nhiệm vụ: Trả lời tự nhiên, hài hước, ngắn gọn. Nếu sếp hỏi tình hình, hãy báo cáo đúng số liệu trên. "
                        f"Nếu thấy còn hàng tồn (chưa chuyển), hãy nịnh sếp gõ lệnh /icloud để em đẩy đi cho sạch kho."
                    )
                    
                    payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_text}], "temperature": 0.7}
                    res = requests.post(url, headers=headers, json=payload, timeout=15)
                    if res.status_code == 200:
                        try:
                            self.bot.reply_to(message, res.json()["choices"][0]["message"]["content"])
                        except (KeyError, IndexError) as e:
                            print(f"⚠️ Lỗi parse AI response: {e}")
                            self.bot.reply_to(message, "Ui não em đang lag 😵‍💫")
                    else:
                        print(f"⚠️ Groq API error: {res.status_code}")
                        self.bot.reply_to(message, "Ui não em đang lag 😵‍💫")
                except requests.exceptions.Timeout:
                    print("⚠️ Timeout khi gọi Groq API")
                    self.bot.reply_to(message, "Mạng kém quá em không rep được! 🥲")
                except requests.exceptions.RequestException as e:
                    print(f"⚠️ Lỗi network: {e}")
                    self.bot.reply_to(message, "Mạng kém quá em không rep được! 🥲")
                except Exception as e:
                    print(f"⚠️ Lỗi fetch_ai_reply: {e}")
                    self.bot.reply_to(message, "Có lỗi gì đó rồi sếp ơi! 😭")
            threading.Thread(target=fetch_ai_reply, daemon=True).start()

        def run_bot():
            self.bot_is_running = True
            self.main_app.bot_is_running = True 
            try:
                print("🤖 Thư ký AI đã lên sóng (Đã có Menu Đóng Băng)...")
                self.bot.infinity_polling()
            except Exception as e: print(f"Lỗi Bot: {e}")
            self.bot_is_running = False
            self.main_app.bot_is_running = False 

        import threading
        threading.Thread(target=run_bot, daemon=True).start()
