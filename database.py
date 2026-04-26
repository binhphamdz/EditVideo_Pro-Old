import sqlite3
import os
from paths import BASE_PATH

DB_PATH = os.path.join(BASE_PATH, "data_system.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

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

    conn.commit()
    conn.close()

init_db()