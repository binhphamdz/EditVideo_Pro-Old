#!/usr/bin/env python3
"""
Test script để kiểm tra TikTok uploader hoạt động bình thường không
Không cần clicker UI, chỉ test upload function riêng
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from tab5_modules.tiktok_uploader import TikTokUploader
import time

def log_callback(msg):
    """Callback để log messages"""
    print(msg)

# === SETUP ===
uploader = TikTokUploader(callback_log=log_callback, profile_name="tiktok_main")

print("=" * 60)
print("🧪 TEST TIKTOK UPLOADER")
print("=" * 60)

# === TEST 1: Initialize driver ===
print("\n[TEST 1] Khởi tạo driver...")
if not uploader.init_driver(headless=False):
    print("❌ Không thể khởi tạo driver")
    sys.exit(1)
print("✅ Driver khởi tạo OK")

# === TEST 2: Check driver alive ===
print("\n[TEST 2] Kiểm tra driver sống...")
if uploader.is_driver_alive():
    print("✅ Driver sống")
else:
    print("❌ Driver không sống")
    sys.exit(1)

# === TEST 3: Load cookies ===
print("\n[TEST 3] Load cookies...")
if uploader.load_cookies():
    print("✅ Cookies loaded")
else:
    print("⚠️ Không có cookies hoặc load failed")

# === TEST 4: Check if logged in ===
print("\n[TEST 4] Kiểm tra login status...")
time.sleep(3)
if uploader.is_already_logged_in():
    uploader.is_logged_in = True
    print("✅ Đã login (hoặc cookies OK)")
else:
    print("⚠️ Cần login lại")
    print("\n>>> Vui lòng login vào TikTok trong browser mở ra...")
    print(">>> Sau khi login xong, enter để tiếp tục...")
    input()
    uploader.save_cookies()
    uploader.is_logged_in = True

# === TEST 5: Find test video ===
print("\n[TEST 5] Tìm video test...")
# Tìm video đầu tiên trong Workspace_Data
video_dir = "Workspace_Data"
test_videos = []
for root, dirs, files in os.walk(video_dir):
    for f in files:
        if f.endswith(('.mp4', '.mov', '.avi')):
            test_videos.append(os.path.join(root, f))
            if len(test_videos) >= 1:
                break
    if test_videos:
        break

if test_videos:
    test_video = test_videos[0]
    print(f"✅ Tìm được video: {test_video}")
    print(f"   Size: {os.path.getsize(test_video) / 1024 / 1024:.2f} MB")
else:
    print("❌ Không tìm thấy video nào để test")
    sys.exit(1)

# === TEST 6: Test upload ===
print("\n[TEST 6] Test upload video...")
print(f">>> Sẽ upload: {os.path.basename(test_video)}")
print(">>> Nếu có lỗi \"invalid session id\", sẽ tự động recovery")

result = uploader.upload_video(
    video_path=test_video,
    title="Test Upload 🎬",
    description="This is a test video upload",
    hashtags="#test #upload"
)

if result:
    print("\n✅ Upload test PASSED!")
else:
    print("\n❌ Upload test FAILED")

# === CLEANUP ===
print("\n[CLEANUP] Đóng driver...")
uploader.close()
print("✅ Done")
