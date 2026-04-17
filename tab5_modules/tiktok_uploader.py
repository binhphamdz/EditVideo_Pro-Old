"""
🎬 TikTok Auto Uploader V2 - Improved with better UI detection
Hỗ trợ: Batch upload, hashtag tự động, delay chống spam, lưu cookies
"""

import os
import time
import threading
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import random


class TikTokUploader:
    def __init__(self, callback_log=None, profile_name="tiktok_profile"):
        """
        Args:
            callback_log: Function để log messages. Signature: callback_log(msg)
            profile_name: Tên profile Chrome để lưu cookies (default: tiktok_profile)
        """
        self.driver = None
        self.callback_log = callback_log or print
        self.is_logged_in = False
        self.uploading = False
        self.profile_name = profile_name
        self.profile_path = os.path.join(os.path.expanduser("~"), ".tiktok_profiles", profile_name)
        self.cookies_file = os.path.join(self.profile_path, "cookies.json")

    def log(self, msg):
        """Log message với timestamp"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.callback_log(f"[{ts}] {msg}")

    def is_driver_alive(self):
        """Kiểm tra xem driver session còn sống không"""
        try:
            if self.driver is None:
                return False
            self.driver.get_window_size()
            return True
        except Exception as e:
            if "invalid session id" in str(e).lower():
                self.log(f"⚠️ Driver session mất")
            return False

    def init_driver(self, headless=False):
        """Khởi tạo Selenium Chrome driver với persistent profile"""
        try:
            options = Options()
            
            os.makedirs(self.profile_path, exist_ok=True)
            options.add_argument(f"user-data-dir={self.profile_path}")
            
            if headless:
                options.add_argument("--headless")
            
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.log("✅ Chrome driver khởi tạo thành công")
            return True
        except Exception as e:
            self.log(f"❌ Lỗi khởi tạo Chrome: {e}")
            return False

    def save_cookies(self):
        """Lưu cookies từ browser"""
        try:
            os.makedirs(self.profile_path, exist_ok=True)
            cookies = self.driver.get_cookies()
            with open(self.cookies_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            self.log(f"💾 Đã lưu cookies")
        except Exception as e:
            self.log(f"⚠️ Lỗi lưu cookies: {e}")

    def load_cookies(self):
        """Load cookies từ file"""
        try:
            if not os.path.exists(self.cookies_file):
                self.log("⚠️ Chưa có cookies lưu sẵn")
                return False
            
            self.driver.get("https://www.tiktok.com")
            time.sleep(2)
            
            with open(self.cookies_file, 'r') as f:
                cookies = json.load(f)
            
            for cookie in cookies:
                try:
                    if 'expiry' in cookie:
                        del cookie['expiry']
                    self.driver.add_cookie(cookie)
                except:
                    pass
            
            self.log("✅ Đã load cookies")
            time.sleep(2)
            self.driver.refresh()
            return True
        except Exception as e:
            self.log(f"⚠️ Lỗi load cookies: {e}")
            return False

    def is_already_logged_in(self):
        """Kiểm tra xem đã login hay chưa"""
        try:
            self.driver.get("https://www.tiktok.com/@me/upload")
            time.sleep(3)
            
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                )
                self.log("✅ Đã có session login")
                return True
            except:
                return False
        except Exception as e:
            self.log(f"⚠️ Lỗi kiểm tra login: {e}")
            return False

    def login(self, wait_manual=True, headless=False):
        """Đăng nhập TikTok (hỗ trợ manual login)"""
        try:
            if not self.driver:
                self.init_driver(headless=headless)

            # Thử load cookies cũ
            if self.load_cookies():
                if self.is_already_logged_in():
                    self.is_logged_in = True
                    return True
            
            # Login thủ công
            self.driver.get("https://www.tiktok.com/login")
            self.log("🔐 Vui lòng đăng nhập vào TikTok trong browser...")
            
            if wait_manual:
                input_msg = f"\n>>> Sau khi login xong, nhấn Enter trong terminal để tiếp tục...\n>>> "
                input(input_msg)
            
            # Chờ redirect về upload page
            try:
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
                )
                self.is_logged_in = True
                self.save_cookies()
                return True
            except:
                self.log("❌ Login thất bại")
                return False
        except Exception as e:
            self.log(f"❌ Lỗi login: {e}")
            return False

    def upload_video(self, video_path, title="", description="", hashtags=""):
        """Upload 1 video lên TikTok"""
        if not self.is_logged_in:
            self.log("⚠️ Chưa đăng nhập!")
            return False

        if not os.path.exists(video_path):
            self.log(f"❌ File không tồn tại: {video_path}")
            return False

        try:
            # === SESSION CHECK ===
            if not self.is_driver_alive():
                self.log("⚠️ Session mất, khôi phục...")
                self.close()
                self.init_driver(headless=False)
                time.sleep(2)
                
                if not self.load_cookies() or not self.is_already_logged_in():
                    self.log("❌ Không thể khôi phục session")
                    return False
                    
                self.log("✅ Đã khôi phục session")
                time.sleep(2)
            
            self.uploading = True
            video_name = os.path.basename(video_path)
            self.log(f"🚀 Bắt đầu upload: {video_name}")

            # === STEP 1: Navigate & Choose File ===
            self.log("1️⃣ Chọn file video...")
            
            try:
                self.driver.get("https://www.tiktok.com/@me/upload")
                time.sleep(3)
            except:
                pass
            
            file_input = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
            )
            file_input.send_keys(os.path.abspath(video_path))
            self.log("✅ File đã chọn")

            # === STEP 2: Wait for upload to complete ===
            self.log("2️⃣ Chờ video xử lý...")
            time.sleep(8)
            
            # Try to find any form element (sign of form being ready)
            try:
                WebDriverWait(self.driver, 45).until(
                    EC.presence_of_element_located((By.XPATH, "//textarea | //input[@type='text'] | //div[@contenteditable='true']"))
                )
                self.log("✅ Form ready")
            except:
                self.log("⚠️ Form elements not found, continuing anyway...")

            # === STEP 3: Fill caption ===
            time.sleep(2)
            self.log("3️⃣ Nhập mô tả...")
            
            caption_text = f"{title}\n\n{description}\n\n{hashtags}".strip() if title or description else hashtags
            caption_filled = False
            
            # Try multiple selectors
            for xpath in ["//textarea", "//div[@contenteditable='true']", "//input[@type='text']"]:
                try:
                    elements = self.driver.find_elements(By.XPATH, xpath)
                    for elem in elements:
                        if elem.is_displayed():
                            elem.click()
                            time.sleep(0.3)
                            elem.send_keys(Keys.CONTROL + 'a')
                            elem.send_keys(caption_text)
                            self.log(f"✅ Nhập: {caption_text[:40]}...")
                            caption_filled = True
                            break
                    if caption_filled:
                        break
                except:
                    continue

            if not caption_filled:
                self.log("⚠️ Không tìm thấy ô caption")

            # === STEP 4: Privacy (optional) ===
            time.sleep(1)
            self.log("4️⃣ Chỉnh quyền riêng tư...")
            try:
                for selector in ["//button[contains(., 'Public')]", "//label[contains(., 'Public')]"]:
                    try:
                        btn = self.driver.find_element(By.XPATH, selector)
                        if btn.is_displayed():
                            btn.click()
                            self.log("✅ Public")
                            break
                    except:
                        pass
            except:
                pass

            # === STEP 5: Post ===
            self.log("5️⃣ Nhấn Post...")
            time.sleep(2)
            
            # Scroll down to find button
            self.driver.execute_script("window.scrollBy(0, 500);")
            time.sleep(2)
            
            for selector in ["//button[contains(., 'Post')]", "//button[contains(., 'Upload')]", "//button[@type='submit']"]:
                try:
                    post_btn = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    post_btn.click()
                    self.log("✅ Nhấn Post")
                    time.sleep(15)  # Wait for upload
                    return True
                except:
                    continue
            
            self.log("⚠️ Không tìm thấy Post button")
            return False

        except Exception as e:
            self.log(f"❌ Lỗi: {str(e)[:80]}")
            return False
        finally:
            self.uploading = False

    def upload_batch(self, videos, delay_seconds=120):
        """Upload batch videos"""
        self.log(f"📦 Bắt đầu upload batch {len(videos)} videos...")
        
        success_count = 0
        for i, video_info in enumerate(videos, 1):
            self.log(f"\n📌 VIDEO {i}/{len(videos)}")
            self.log("=" * 60)
            
            result = self.upload_video(
                video_path=video_info.get('path', video_info),
                title=video_info.get('title', ''),
                description=video_info.get('description', ''),
                hashtags=video_info.get('hashtags', '')
            )
            
            if result:
                success_count += 1
            
            if i < len(videos):
                self.log(f"⏳ Chờ {delay_seconds}s trước video tiếp theo...")
                time.sleep(delay_seconds)
        
        self.log(f"\n{'=' * 60}")
        self.log(f"🎊 BATCH UPLOAD XONG!")
        self.log(f"✅ Thành công: {success_count}")
        self.log(f"❌ Thất bại: {len(videos) - success_count}")
        self.log(f"{'=' * 60}\n")

    def close(self):
        """Đóng driver"""
        try:
            if self.driver:
                self.driver.quit()
                self.log("✅ Đã đóng driver")
        except:
            pass
