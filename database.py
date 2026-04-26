import sqlite3
import os
import threading
from paths import BASE_PATH

DB_PATH = os.path.join(BASE_PATH, "data_system.db")

# ============================================================
# [MỚI] Ổ khóa toàn cục bảo vệ concurrent access tới Database
# ============================================================
db_lock = threading.RLock()

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    
    # [QUAN TRỌNG] Bật công tắc Khóa Ngoại để ON DELETE CASCADE tự động dọn rác
    conn.execute("PRAGMA foreign_keys = ON;")
    # Tăng cache size để giảm lock contention
    conn.execute("PRAGMA cache_size = 10000;")
    
    return conn

def get_or_create_project(proj_name):
    """Lấy ID của Project, nếu chưa có thì tự động tạo mới để chống crash"""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM projects WHERE name = ?", (proj_name,))
        row = cursor.fetchone()
        if row:
            pid = row['id']
        else:
            cursor.execute("INSERT INTO projects (name) VALUES (?)", (proj_name,))
            pid = cursor.lastrowid
        conn.commit()
        conn.close()
        return pid

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Bảng Projects (Bổ sung context, ảnh mẫu, links)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            product_name TEXT,
            product_context TEXT,
            ref_img_1 TEXT,
            ref_img_2 TEXT,
            product_links TEXT,
            shopee_out_of_stock INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Bảng Voices (Của Tab 1)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            file_name TEXT NOT NULL,
            usage_count INTEGER DEFAULT 0,
            srt_cache TEXT,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
            UNIQUE(project_id, file_name)
        )
    ''')

    # 3. Bảng Brolls (Cảnh trám - Bổ sung keep_audio và status thùng rác)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS brolls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            file_name TEXT NOT NULL,
            duration REAL DEFAULT 0,
            description TEXT,
            usage_count INTEGER DEFAULT 0,
            keep_audio INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active', 
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
            UNIQUE(project_id, file_name)
        )
    ''')

    # 4. Bảng Shopee Jobs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS shopee_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            video_name TEXT UNIQUE,
            product_name TEXT,
            links TEXT,
            caption TEXT,
            status TEXT DEFAULT 'Chưa đăng',
            device_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        )
    ''')

    # 5. Bảng Rendered Videos (Thành phẩm - Thay thế file CSV cũ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rendered_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            voice_name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'Chưa chuyển',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

# ============================================================
# CÁC HÀM THAO TÁC BẢNG rendered_videos
# ============================================================

def log_rendered_video(project_name, voice_name, file_path):
    """Thêm 1 video thành phẩm vào Database sau khi render xong"""
    with db_lock:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO rendered_videos (project_name, voice_name, file_path) VALUES (?, ?, ?)",
                (project_name, voice_name, file_path)
            )
            conn.commit()
        finally:
            conn.close()

def get_all_rendered_videos():
    """Lấy toàn bộ danh sách video thành phẩm, mới nhất lên trên"""
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT created_at, project_name, voice_name, file_path, status FROM rendered_videos ORDER BY id DESC")
            return cursor.fetchall()
        finally:
            conn.close()

def update_rendered_video_status(file_path, new_status):
    """Cập nhật trạng thái (Đã chuyển / Chưa chuyển) theo đường dẫn file"""
    with db_lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE rendered_videos SET status = ? WHERE file_path = ?", (new_status, file_path))
            conn.commit()
        finally:
            conn.close()

def update_rendered_video_path(old_path, new_path):
    """Cập nhật đường dẫn khi file bị đổi tên / di chuyển"""
    with db_lock:
        conn = get_connection()
        try:
            conn.execute("UPDATE rendered_videos SET file_path = ? WHERE file_path = ?", (new_path, old_path))
            conn.commit()
        finally:
            conn.close()

def delete_rendered_videos(file_paths):
    """Xoá nhiều bản ghi theo đường dẫn (khi xóa video khỏi kho)"""
    with db_lock:
        conn = get_connection()
        try:
            conn.executemany("DELETE FROM rendered_videos WHERE file_path = ?", [(p,) for p in file_paths])
            conn.commit()
        finally:
            conn.close()

def get_pending_rendered_videos():
    """Lấy các video chưa chuyển sang iPhone (dùng cho bot iCloud)"""
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM rendered_videos WHERE status != 'Đã chuyển'")
            return [r['file_path'] for r in cursor.fetchall()]
        finally:
            conn.close()

init_db()