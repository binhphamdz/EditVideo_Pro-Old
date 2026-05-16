import sqlite3
import os
import threading
import json
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

    # [MIGRATION] Thêm cột last_used vào voices nếu DB cũ chưa có
    try:
        cursor.execute("ALTER TABLE voices ADD COLUMN last_used TIMESTAMP")
        conn.commit()
    except Exception:
        pass  # Cột đã tồn tại, bỏ qua

    # [MIGRATION] Thêm cột srt_origin vào voices nếu DB cũ chưa có
    try:
        cursor.execute("ALTER TABLE voices ADD COLUMN srt_origin INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # Cột đã tồn tại, bỏ qua

    # [MIGRATION] Lưu timeline vào DB thay cho project_data.json
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN timeline_json TEXT DEFAULT '[]'")
        conn.commit()
    except Exception:
        pass

    # [MIGRATION] Link sản phẩm TikTok dùng cho tab auto đăng web.
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN tiktok_link TEXT")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE shopee_jobs ADD COLUMN tiktok_link TEXT")
        conn.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE rendered_videos ADD COLUMN tiktok_link TEXT")
        conn.commit()
    except Exception:
        pass

    for sql in [
        "ALTER TABLE voices ADD COLUMN reserved_at TIMESTAMP",
        "ALTER TABLE voices ADD COLUMN reserved_by_job TEXT",
        "ALTER TABLE brolls ADD COLUMN bad_count INTEGER DEFAULT 0",
        "ALTER TABLE brolls ADD COLUMN freeze_score REAL DEFAULT 0",
        "ALTER TABLE brolls ADD COLUMN last_error TEXT",
        "ALTER TABLE brolls ADD COLUMN scene_type TEXT",
        "ALTER TABLE brolls ADD COLUMN ai_recognition_log TEXT",
    ]:
        try:
            cursor.execute(sql)
            conn.commit()
        except Exception:
            pass

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
            tiktok_link TEXT,
            shopee_out_of_stock INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            timeline_json TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Bảng mapping project theo profile để thay projects_list.json
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_projects (
            project_pid TEXT PRIMARY KEY,
            profile_name TEXT NOT NULL,
            project_name TEXT NOT NULL,
            created_at REAL,
            status TEXT DEFAULT 'active'
        )
    ''')

 # 2. Bảng Voices (Bổ sung cột last_used)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS voices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            file_name TEXT NOT NULL,
            usage_count INTEGER DEFAULT 0,
            srt_cache TEXT,
            srt_origin INTEGER DEFAULT 0,
            last_used TIMESTAMP, 
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
            bad_count INTEGER DEFAULT 0,
            freeze_score REAL DEFAULT 0,
            last_error TEXT,
            scene_type TEXT,
            ai_recognition_log TEXT,
            keep_audio INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active', 
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
            UNIQUE(project_id, file_name)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS render_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            profile_name TEXT,
            chat_id TEXT,
            label TEXT,
            project_name TEXT NOT NULL,
            voice_name TEXT NOT NULL,
            proj_dir TEXT,
            status TEXT DEFAULT 'queued',
            output_path TEXT,
            error TEXT,
            attempts INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP
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
            tiktok_link TEXT,
            caption TEXT,
            status TEXT DEFAULT 'Chưa đăng',
            device_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
        )
    ''')

    # 5. Bảng Rendered Videos (Thành phẩm - Thay thế file CSV cũ)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS rendered_videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            voice_name TEXT NOT NULL,
            file_path TEXT NOT NULL UNIQUE,
            tiktok_link TEXT,
            status TEXT DEFAULT 'Chưa chuyển',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 6. Bảng Script Styles (Phong cách kịch bản)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS script_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT NOT NULL,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(profile_name, name)
        )
    ''')

    # 7. Bảng Script Style Samples (SRT dùng để học phong cách)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS script_style_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            style_id INTEGER NOT NULL,
            source_name TEXT,
            srt_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (style_id) REFERENCES script_styles (id) ON DELETE CASCADE
        )
    ''')

    # 8. Bảng Project Scripts (Kịch bản theo project)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            keys_json TEXT,
            style_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
            FOREIGN KEY (style_id) REFERENCES script_styles (id) ON DELETE SET NULL
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
            cursor = conn.cursor()
            cursor.execute("SELECT tiktok_link FROM projects WHERE name = ?", (project_name,))
            project = cursor.fetchone()
            tiktok_link = project["tiktok_link"] if project and "tiktok_link" in project.keys() else ""
            conn.execute(
                """
                INSERT INTO rendered_videos (project_name, voice_name, file_path, tiktok_link)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    project_name = excluded.project_name,
                    voice_name = excluded.voice_name,
                    tiktok_link = COALESCE(NULLIF(rendered_videos.tiktok_link, ''), excluded.tiktok_link)
                """,
                (project_name, voice_name, file_path, tiktok_link or "")
            )
            conn.commit()
        finally:
            conn.close()

def get_all_rendered_videos(profile_name=None):
    """Lấy danh sách video thành phẩm, mới nhất lên trên."""
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if profile_name:
                names = get_project_names_for_profile(profile_name)
                if not names:
                    return []
                placeholders = ",".join(["?"] * len(names))
                cursor.execute(
                    f"""
                    SELECT rv.created_at, rv.project_name, rv.voice_name, rv.file_path,
                           COALESCE(NULLIF(rv.tiktok_link, ''), p.tiktok_link, '') AS tiktok_link,
                           rv.status
                    FROM rendered_videos rv
                    LEFT JOIN projects p ON p.name = rv.project_name
                    WHERE rv.project_name IN ({placeholders})
                    ORDER BY rv.id DESC
                    """,
                    names,
                )
            else:
                cursor.execute(
                    """
                    SELECT rv.created_at, rv.project_name, rv.voice_name, rv.file_path,
                           COALESCE(NULLIF(rv.tiktok_link, ''), p.tiktok_link, '') AS tiktok_link,
                           rv.status
                    FROM rendered_videos rv
                    LEFT JOIN projects p ON p.name = rv.project_name
                    ORDER BY rv.id DESC
                    """
                )
            return cursor.fetchall()
        finally:
            conn.close()

def update_rendered_video_tiktok_link(file_path, tiktok_link):
    """Cập nhật link sản phẩm TikTok nhập tay theo từng video thành phẩm."""
    with db_lock:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE rendered_videos SET tiktok_link = ? WHERE file_path = ?",
                (str(tiktok_link or "").strip(), file_path),
            )
            conn.commit()
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

def get_pending_rendered_videos(profile_name=None):
    """Lấy các video chưa chuyển sang iPhone (dùng cho bot iCloud)."""
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if profile_name:
                names = get_project_names_for_profile(profile_name)
                if not names:
                    return []
                placeholders = ",".join(["?"] * len(names))
                cursor.execute(
                    f"SELECT file_path FROM rendered_videos WHERE status != 'Đã chuyển' AND project_name IN ({placeholders})",
                    names,
                )
            else:
                cursor.execute("SELECT file_path FROM rendered_videos WHERE status != 'Đã chuyển'")
            return [r["file_path"] for r in cursor.fetchall()]
        finally:
            conn.close()


def create_render_jobs(batch_id, profile_name, chat_id, label, render_queue):
    """Tạo job render và giữ chỗ voice cho một batch bot."""
    job_ids = []
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            for voice_name, proj_dir, project_name in render_queue:
                cursor.execute(
                    """
                    INSERT INTO render_jobs (batch_id, profile_name, chat_id, label, project_name, voice_name, proj_dir, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
                    """,
                    (str(batch_id), str(profile_name or ""), str(chat_id or ""), str(label or ""), project_name, voice_name, proj_dir),
                )
                job_id = cursor.lastrowid
                job_ids.append(job_id)
                cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
                project_row = cursor.fetchone()
                if project_row:
                    project_id = project_row["id"]
                else:
                    cursor.execute("INSERT INTO projects (name) VALUES (?)", (project_name,))
                    project_id = cursor.lastrowid
                cursor.execute(
                    """
                    UPDATE voices
                    SET reserved_at = datetime('now', 'localtime'),
                        reserved_by_job = ?,
                        last_used = datetime('now', 'localtime')
                    WHERE project_id = ? AND file_name = ?
                    """,
                    (str(job_id), project_id, voice_name),
                )
            conn.commit()
            return job_ids
        finally:
            conn.close()


def update_render_job(job_id, status, output_path=None, error=None):
    with db_lock:
        conn = get_connection()
        try:
            fields = ["status = ?"]
            params = [status]
            if status == "running":
                fields.append("started_at = datetime('now', 'localtime')")
                fields.append("attempts = attempts + 1")
            if status in ("done", "failed", "cancelled"):
                fields.append("finished_at = datetime('now', 'localtime')")
            if output_path is not None:
                fields.append("output_path = ?")
                params.append(output_path)
            if error is not None:
                fields.append("error = ?")
                params.append(str(error)[:1200])
            params.append(job_id)
            conn.execute(f"UPDATE render_jobs SET {', '.join(fields)} WHERE id = ?", params)
            conn.commit()
        finally:
            conn.close()


def list_recent_render_jobs(limit=20, profile_name=None):
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if profile_name:
                cursor.execute(
                    """
                    SELECT * FROM render_jobs
                    WHERE profile_name = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (profile_name, int(limit)),
                )
            else:
                cursor.execute("SELECT * FROM render_jobs ORDER BY id DESC LIMIT ?", (int(limit),))
            return cursor.fetchall()
        finally:
            conn.close()


def cancel_queued_render_jobs(profile_name=None):
    with db_lock:
        conn = get_connection()
        try:
            if profile_name:
                cur = conn.execute(
                    """
                    UPDATE render_jobs
                    SET status = 'cancelled', finished_at = datetime('now', 'localtime')
                    WHERE status = 'queued' AND profile_name = ?
                    """,
                    (profile_name,),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE render_jobs
                    SET status = 'cancelled', finished_at = datetime('now', 'localtime')
                    WHERE status = 'queued'
                    """
                )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def mark_broll_health(project_name, file_name, freeze_score=0.0, error=""):
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
            project_row = cursor.fetchone()
            if project_row:
                project_id = project_row["id"]
            else:
                cursor.execute("INSERT INTO projects (name) VALUES (?)", (project_name,))
                project_id = cursor.lastrowid
            freeze_score = float(freeze_score or 0.0)
            bad_increment = 1 if freeze_score >= 1.5 or error else 0
            conn.execute(
                """
                UPDATE brolls
                SET freeze_score = MAX(COALESCE(freeze_score, 0), ?),
                    bad_count = COALESCE(bad_count, 0) + ?,
                    last_error = CASE WHEN ? != '' THEN ? ELSE last_error END,
                    status = CASE WHEN COALESCE(bad_count, 0) + ? >= 3 THEN 'inactive' ELSE status END
                WHERE project_id = ? AND file_name = ?
                """,
                (freeze_score, bad_increment, str(error or ""), str(error or "")[:500], bad_increment, project_id, file_name),
            )
            conn.commit()
        finally:
            conn.close()


def upsert_script_style(profile_name, name, prompt, notes=""):
    profile_name = str(profile_name or "").strip()
    name = str(name or "").strip()
    prompt = str(prompt or "").strip()
    notes = str(notes or "").strip()
    if not profile_name or not name or not prompt:
        return None

    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO script_styles (profile_name, name, prompt, notes)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(profile_name, name) DO UPDATE SET
                    prompt=excluded.prompt,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (profile_name, name, prompt, notes),
            )
            conn.commit()
            cursor.execute(
                "SELECT id FROM script_styles WHERE profile_name = ? AND name = ?",
                (profile_name, name),
            )
            row = cursor.fetchone()
            return row["id"] if row else None
        finally:
            conn.close()


def add_script_style_sample(style_id, source_name, srt_text):
    if not style_id:
        return
    with db_lock:
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO script_style_samples (style_id, source_name, srt_text) VALUES (?, ?, ?)",
                (style_id, str(source_name or "").strip(), str(srt_text or "")),
            )
            conn.commit()
        finally:
            conn.close()


def list_script_styles(profile_name):
    profile_name = str(profile_name or "").strip()
    if not profile_name:
        return []
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, prompt, notes, updated_at FROM script_styles WHERE profile_name = ? ORDER BY updated_at DESC",
                (profile_name,),
            )
            return cursor.fetchall()
        finally:
            conn.close()


def add_project_script(project_name, title, content, keys=None, style_id=None):
    project_name = str(project_name or "").strip()
    content = str(content or "").strip()
    if not project_name or not content:
        return None

    keys_json = ""
    try:
        keys_json = json.dumps(keys or [], ensure_ascii=False)
    except Exception:
        keys_json = ""

    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            project_id = get_or_create_project(project_name)
            cursor.execute(
                """
                INSERT INTO project_scripts (project_id, title, content, keys_json, style_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, str(title or "").strip(), content, keys_json, style_id),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()


def list_project_scripts(project_name):
    project_name = str(project_name or "").strip()
    if not project_name:
        return []
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
            proj = cursor.fetchone()
            if not proj:
                return []
            cursor.execute(
                """
                SELECT ps.id, ps.title, ps.created_at, ss.name as style_name
                FROM project_scripts ps
                LEFT JOIN script_styles ss ON ss.id = ps.style_id
                WHERE ps.project_id = ?
                ORDER BY ps.id DESC
                """,
                (proj["id"],),
            )
            return cursor.fetchall()
        finally:
            conn.close()


def get_project_script(script_id):
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ps.id, ps.title, ps.content, ps.keys_json, ps.created_at, ps.style_id,
                       ss.name as style_name, ss.prompt as style_prompt
                FROM project_scripts ps
                LEFT JOIN script_styles ss ON ss.id = ps.style_id
                WHERE ps.id = ?
                """,
                (script_id,),
            )
            return cursor.fetchone()
        finally:
            conn.close()


def delete_project_script(script_id):
    with db_lock:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM project_scripts WHERE id = ?", (script_id,))
            conn.commit()
        finally:
            conn.close()


def get_project_names_for_profile(profile_name):
    """Lấy danh sách project_name theo profile để lọc dữ liệu."""
    profile_name = str(profile_name or "").strip()
    if not profile_name:
        return []

    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT project_name FROM app_projects WHERE profile_name = ?",
                (profile_name,),
            )
            return [row["project_name"] for row in cursor.fetchall()]
        finally:
            conn.close()


def get_project_ids_for_profile(profile_name):
    """Lấy danh sách project_id (bảng projects) theo profile."""
    profile_name = str(profile_name or "").strip()
    if not profile_name:
        return []

    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT p.id
                FROM projects p
                JOIN app_projects ap ON ap.project_name = p.name
                WHERE ap.profile_name = ?
                """,
                (profile_name,),
            )
            return [row["id"] for row in cursor.fetchall()]
        finally:
            conn.close()


# ============================================================
# CÁC HÀM THAO TÁC DỮ LIỆU PROJECT (THAY JSON)
# ============================================================

def get_app_projects(profile_name):
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT project_pid, project_name, created_at, status
                FROM app_projects
                WHERE profile_name = ?
                ORDER BY created_at DESC
                """,
                (profile_name,),
            )
            rows = cursor.fetchall()
            projects = {}
            for row in rows:
                projects[row["project_pid"]] = {
                    "name": row["project_name"],
                    "created_at": float(row["created_at"] or 0),
                    "status": row["status"] or "active",
                }
            return projects
        finally:
            conn.close()


def upsert_app_projects(profile_name, projects_dict):
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            # Đồng bộ dạng full-snapshot theo profile hiện tại
            cursor.execute("DELETE FROM app_projects WHERE profile_name = ?", (profile_name,))
            for pid, pdata in (projects_dict or {}).items():
                proj_name = str((pdata or {}).get("name", "")).strip()
                if not proj_name:
                    continue
                cursor.execute(
                    """
                    INSERT INTO app_projects (project_pid, profile_name, project_name, created_at, status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        str(pid),
                        profile_name,
                        proj_name,
                        float((pdata or {}).get("created_at") or 0),
                        str((pdata or {}).get("status", "active") or "active"),
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def get_project_payload(project_name):
    default_payload = {
        "videos": {},
        "trash": {},
        "timeline": [],
        "product_context": "",
        "product_name": "",
        "tiktok_link": "",
        "shopee_out_of_stock": False,
        "product_links": ["", "", "", "", "", ""],
        "ref_img_1": "",
        "ref_img_2": "",
        "voice_usage": {},
        "voice_srt_cache": {},
        "voice_srt_origin": {},
    }

    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, product_name, product_context, ref_img_1, ref_img_2,
                       product_links, tiktok_link, shopee_out_of_stock, timeline_json
                FROM projects
                WHERE name = ?
                """,
                (project_name,),
            )
            p_row = cursor.fetchone()
            if not p_row:
                return default_payload

            db_proj_id = p_row["id"]
            payload = dict(default_payload)
            payload["product_name"] = p_row["product_name"] or ""
            payload["tiktok_link"] = p_row["tiktok_link"] or ""
            payload["product_context"] = p_row["product_context"] or ""
            payload["ref_img_1"] = p_row["ref_img_1"] or ""
            payload["ref_img_2"] = p_row["ref_img_2"] or ""
            payload["shopee_out_of_stock"] = bool(p_row["shopee_out_of_stock"])

            try:
                links = json.loads(p_row["product_links"] or "[]")
                if isinstance(links, list):
                    payload["product_links"] = (links + ["", "", "", "", "", ""])[:6]
            except Exception:
                pass

            try:
                timeline = json.loads(p_row["timeline_json"] or "[]")
                if isinstance(timeline, list):
                    payload["timeline"] = timeline
            except Exception:
                pass

            cursor.execute(
                "SELECT file_name, usage_count, srt_cache, srt_origin FROM voices WHERE project_id = ?",
                (db_proj_id,),
            )
            for row in cursor.fetchall():
                payload["voice_usage"][row["file_name"]] = int(row["usage_count"] or 0)
                if row["srt_cache"]:
                    payload["voice_srt_cache"][row["file_name"]] = row["srt_cache"]
                if row["srt_origin"]:
                    payload["voice_srt_origin"][row["file_name"]] = True

            cursor.execute(
                "SELECT file_name, duration, description, usage_count, keep_audio, scene_type, ai_recognition_log, status FROM brolls WHERE project_id = ?",
                (db_proj_id,),
            )
            for row in cursor.fetchall():
                item = {
                    "duration": float(row["duration"] or 0),
                    "description": row["description"] or "",
                    "usage_count": int(row["usage_count"] or 0),
                    "keep_audio": bool(row["keep_audio"]),
                    "scene_type": row["scene_type"] or "",
                    "ai_recognition_log": row["ai_recognition_log"] or "",
                }
                if row["status"] == "trash":
                    payload["trash"][row["file_name"]] = item
                else:
                    payload["videos"][row["file_name"]] = item

            return payload
        finally:
            conn.close()


def save_project_payload(project_name, payload, project_status="active"):
    payload = payload or {}
    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            db_proj_id = get_or_create_project(project_name)

            product_links = payload.get("product_links", ["", "", "", "", "", ""])
            if not isinstance(product_links, list):
                product_links = [""] * 6
            product_links = (product_links + ["", "", "", "", "", ""])[:6]

            cursor.execute(
                """
                UPDATE projects
                SET product_name = ?,
                    product_context = ?,
                    ref_img_1 = ?,
                    ref_img_2 = ?,
                    product_links = ?,
                    tiktok_link = ?,
                    shopee_out_of_stock = ?,
                    status = ?,
                    timeline_json = ?
                WHERE id = ?
                """,
                (
                    payload.get("product_name", ""),
                    payload.get("product_context", ""),
                    payload.get("ref_img_1", ""),
                    payload.get("ref_img_2", ""),
                    json.dumps(product_links, ensure_ascii=False),
                    payload.get("tiktok_link", ""),
                    1 if payload.get("shopee_out_of_stock", False) else 0,
                    project_status or "active",
                    json.dumps(payload.get("timeline", []), ensure_ascii=False),
                    db_proj_id,
                ),
            )

            # Voices: upsert usage + srt, giữ nguyên last_used/status đã có.
            voice_usage = payload.get("voice_usage", {}) or {}
            voice_srt = payload.get("voice_srt_cache", {}) or {}
            voice_srt_origin = payload.get("voice_srt_origin", {}) or {}

            cursor.execute(
                "SELECT file_name, last_used, status, srt_origin FROM voices WHERE project_id = ?",
                (db_proj_id,),
            )
            existing_voice_meta = {
                r["file_name"]: (r["last_used"], r["status"] or "active", int(r["srt_origin"] or 0))
                for r in cursor.fetchall()
            }

            all_voice_names = set(voice_usage.keys()) | set(voice_srt.keys())
            for file_name in all_voice_names:
                last_used, status, existing_origin = existing_voice_meta.get(file_name, (None, "active", 0))
                origin_val = int(voice_srt_origin.get(file_name, existing_origin) or 0)
                cursor.execute(
                    """
                    INSERT INTO voices (project_id, file_name, usage_count, srt_cache, srt_origin, last_used, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, file_name) DO UPDATE SET
                        usage_count = excluded.usage_count,
                        srt_cache = excluded.srt_cache,
                        srt_origin = excluded.srt_origin
                    """,
                    (
                        db_proj_id,
                        file_name,
                        int(voice_usage.get(file_name, 0) or 0),
                        str(voice_srt.get(file_name, "") or ""),
                        origin_val,
                        last_used,
                        status,
                    ),
                )

            # Broll: upsert theo dữ liệu hiện tại từ payload.
            videos = payload.get("videos", {}) or {}
            trash = payload.get("trash", {}) or {}

            for file_name, info in videos.items():
                info = info or {}
                cursor.execute(
                    """
                    INSERT INTO brolls (project_id, file_name, duration, description, usage_count, keep_audio, scene_type, ai_recognition_log, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    ON CONFLICT(project_id, file_name) DO UPDATE SET
                        duration = excluded.duration,
                        description = excluded.description,
                        usage_count = excluded.usage_count,
                        keep_audio = excluded.keep_audio,
                        scene_type = excluded.scene_type,
                        ai_recognition_log = excluded.ai_recognition_log,
                        status = 'active'
                    """,
                    (
                        db_proj_id,
                        file_name,
                        float(info.get("duration", 0) or 0),
                        str(info.get("description", "") or ""),
                        int(info.get("usage_count", 0) or 0),
                        1 if info.get("keep_audio", False) else 0,
                        str(info.get("scene_type", "") or ""),
                        str(info.get("ai_recognition_log", "") or ""),
                    ),
                )

            for file_name, info in trash.items():
                info = info or {}
                cursor.execute(
                    """
                    INSERT INTO brolls (project_id, file_name, duration, description, usage_count, keep_audio, scene_type, ai_recognition_log, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'trash')
                    ON CONFLICT(project_id, file_name) DO UPDATE SET
                        duration = excluded.duration,
                        description = excluded.description,
                        usage_count = excluded.usage_count,
                        keep_audio = excluded.keep_audio,
                        scene_type = excluded.scene_type,
                        ai_recognition_log = excluded.ai_recognition_log,
                        status = 'trash'
                    """,
                    (
                        db_proj_id,
                        file_name,
                        float(info.get("duration", 0) or 0),
                        str(info.get("description", "") or ""),
                        int(info.get("usage_count", 0) or 0),
                        1 if info.get("keep_audio", False) else 0,
                        str(info.get("scene_type", "") or ""),
                        str(info.get("ai_recognition_log", "") or ""),
                    ),
                )

            conn.commit()
        finally:
            conn.close()


def rename_project_name_preserve_data(old_name, new_name, profile_name=None, project_pid=None):
    old_name = str(old_name or "").strip()
    new_name = str(new_name or "").strip()
    if not old_name or not new_name:
        return False, "Tên project không hợp lệ."
    if old_name == new_name:
        return True, "Không có thay đổi tên."

    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM projects WHERE name = ?", (old_name,))
            old_row = cursor.fetchone()
            if not old_row:
                return False, f"Không tìm thấy project cũ trong DB: {old_name}"
            old_id = old_row["id"]

            cursor.execute("SELECT COUNT(*) c FROM brolls WHERE project_id = ?", (old_id,))
            old_brolls = int(cursor.fetchone()["c"] or 0)
            cursor.execute("SELECT COUNT(*) c FROM voices WHERE project_id = ?", (old_id,))
            old_voices = int(cursor.fetchone()["c"] or 0)

            cursor.execute("SELECT id FROM projects WHERE name = ?", (new_name,))
            new_row = cursor.fetchone()

            if new_row and new_row["id"] != old_id:
                new_id = new_row["id"]
                cursor.execute("SELECT COUNT(*) c FROM brolls WHERE project_id = ?", (new_id,))
                new_brolls = int(cursor.fetchone()["c"] or 0)
                cursor.execute("SELECT COUNT(*) c FROM voices WHERE project_id = ?", (new_id,))
                new_voices = int(cursor.fetchone()["c"] or 0)

                # Nếu cả 2 bên đều có dữ liệu, thực hiện gộp an toàn.
                if (old_brolls > 0 or old_voices > 0) and (new_brolls > 0 or new_voices > 0):
                    # Gộp brolls: thêm file chưa có, cập nhật mô tả/âm thanh còn trống.
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO brolls
                        (project_id, file_name, duration, description, usage_count, keep_audio, scene_type, ai_recognition_log, status)
                        SELECT ?, file_name, duration, description, usage_count, keep_audio, scene_type, ai_recognition_log, status
                        FROM brolls
                        WHERE project_id = ?
                        """,
                        (new_id, old_id),
                    )
                    cursor.execute(
                        """
                        UPDATE brolls
                        SET
                            description = CASE
                                WHEN description IS NULL OR TRIM(description) = ''
                                THEN (SELECT description FROM brolls b2 WHERE b2.project_id = ? AND b2.file_name = brolls.file_name)
                                ELSE description
                            END,
                            keep_audio = CASE
                                WHEN keep_audio = 0
                                THEN COALESCE((SELECT keep_audio FROM brolls b2 WHERE b2.project_id = ? AND b2.file_name = brolls.file_name), keep_audio)
                                ELSE keep_audio
                            END,
                            duration = CASE
                                WHEN duration IS NULL OR duration = 0
                                THEN COALESCE((SELECT duration FROM brolls b2 WHERE b2.project_id = ? AND b2.file_name = brolls.file_name), duration)
                                ELSE duration
                            END,
                            usage_count = CASE
                                WHEN COALESCE((SELECT usage_count FROM brolls b2 WHERE b2.project_id = ? AND b2.file_name = brolls.file_name), 0) > usage_count
                                THEN (SELECT usage_count FROM brolls b2 WHERE b2.project_id = ? AND b2.file_name = brolls.file_name)
                                ELSE usage_count
                            END,
                            scene_type = CASE
                                WHEN scene_type IS NULL OR TRIM(scene_type) = ''
                                THEN (SELECT scene_type FROM brolls b2 WHERE b2.project_id = ? AND b2.file_name = brolls.file_name)
                                ELSE scene_type
                            END,
                            ai_recognition_log = CASE
                                WHEN ai_recognition_log IS NULL OR TRIM(ai_recognition_log) = ''
                                THEN (SELECT ai_recognition_log FROM brolls b2 WHERE b2.project_id = ? AND b2.file_name = brolls.file_name)
                                ELSE ai_recognition_log
                            END
                        WHERE project_id = ?
                        """,
                        (old_id, old_id, old_id, old_id, old_id, old_id, old_id, new_id),
                    )

                    # Gộp voices: thêm file chưa có, cập nhật srt/usage còn trống.
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO voices
                        (project_id, file_name, usage_count, srt_cache, srt_origin, last_used, status)
                        SELECT ?, file_name, usage_count, srt_cache, srt_origin, last_used, status
                        FROM voices
                        WHERE project_id = ?
                        """,
                        (new_id, old_id),
                    )
                    cursor.execute(
                        """
                        UPDATE voices
                        SET
                            srt_cache = CASE
                                WHEN srt_cache IS NULL OR TRIM(srt_cache) = ''
                                THEN (SELECT srt_cache FROM voices v2 WHERE v2.project_id = ? AND v2.file_name = voices.file_name)
                                ELSE srt_cache
                            END,
                            srt_origin = CASE
                                WHEN srt_origin IS NULL OR srt_origin = 0
                                THEN COALESCE((SELECT srt_origin FROM voices v2 WHERE v2.project_id = ? AND v2.file_name = voices.file_name), srt_origin)
                                ELSE srt_origin
                            END,
                            usage_count = CASE
                                WHEN COALESCE((SELECT usage_count FROM voices v2 WHERE v2.project_id = ? AND v2.file_name = voices.file_name), 0) > usage_count
                                THEN (SELECT usage_count FROM voices v2 WHERE v2.project_id = ? AND v2.file_name = voices.file_name)
                                ELSE usage_count
                            END,
                            last_used = CASE
                                WHEN last_used IS NULL
                                THEN (SELECT last_used FROM voices v2 WHERE v2.project_id = ? AND v2.file_name = voices.file_name)
                                ELSE last_used
                            END
                        WHERE project_id = ?
                        """,
                        (old_id, old_id, old_id, old_id, old_id, new_id),
                    )

                    # Dời scripts và job sang project mới.
                    cursor.execute("UPDATE project_scripts SET project_id = ? WHERE project_id = ?", (new_id, old_id))
                    cursor.execute("UPDATE shopee_jobs SET project_id = ? WHERE project_id = ?", (new_id, old_id))
                    cursor.execute(
                        "UPDATE rendered_videos SET project_name = ? WHERE project_name = ?",
                        (new_name, old_name),
                    )

                    # Cập nhật mapping project theo profile/pid.
                    if profile_name and project_pid:
                        cursor.execute(
                            "UPDATE app_projects SET project_name = ? WHERE profile_name = ? AND project_pid = ?",
                            (new_name, str(profile_name), str(project_pid)),
                        )
                    else:
                        cursor.execute(
                            "UPDATE app_projects SET project_name = ? WHERE project_name = ?",
                            (new_name, old_name),
                        )

                    # Xoá project cũ sau khi gộp.
                    cursor.execute("DELETE FROM projects WHERE id = ?", (old_id,))
                    conn.commit()
                    return True, (
                        f"Đã gộp dữ liệu vào project '{new_name}' (broll={new_brolls}, voice={new_voices})."
                    )

                # Nếu tên mới thực chất thuộc 1 project đã có dữ liệu,
                # nhưng project hiện tại chỉ là row rỗng (thường do lệch rename cũ),
                # thì chuyển mapping sang tên mới thay vì chặn.
                if old_brolls == 0 and old_voices == 0 and (new_brolls > 0 or new_voices > 0):
                    if profile_name and project_pid:
                        cursor.execute(
                            "UPDATE app_projects SET project_name = ? WHERE profile_name = ? AND project_pid = ?",
                            (new_name, str(profile_name), str(project_pid)),
                        )
                    else:
                        cursor.execute(
                            "UPDATE app_projects SET project_name = ? WHERE project_name = ?",
                            (new_name, old_name),
                        )

                    cursor.execute(
                        "UPDATE rendered_videos SET project_name = ? WHERE project_name = ?",
                        (new_name, old_name),
                    )
                    cursor.execute("DELETE FROM projects WHERE id = ?", (old_id,))
                    conn.commit()
                    return True, (
                        f"Đã đồng bộ về project có sẵn '{new_name}' "
                        f"(broll={new_brolls}, voice={new_voices})."
                    )

                # Nếu row tên mới chỉ là row rỗng do bug cũ -> xóa để nhường tên.
                if new_brolls == 0 and new_voices == 0:
                    cursor.execute("DELETE FROM projects WHERE id = ?", (new_id,))
                else:
                    usage_hint = ""
                    if profile_name:
                        cursor.execute(
                            "SELECT project_pid FROM app_projects WHERE profile_name = ? AND project_name = ? LIMIT 1",
                            (str(profile_name), new_name),
                        )
                        in_current_profile = cursor.fetchone()
                        if in_current_profile:
                            usage_hint = f" Tên này đang nằm trong tài khoản hiện tại (PID={in_current_profile['project_pid']})."
                        else:
                            cursor.execute(
                                "SELECT profile_name FROM app_projects WHERE project_name = ? LIMIT 1",
                                (new_name,),
                            )
                            in_other_profile = cursor.fetchone()
                            if in_other_profile:
                                usage_hint = f" Tên này đang thuộc tài khoản khác: {in_other_profile['profile_name']}."

                    return False, (
                        f"Tên mới '{new_name}' đang trùng với project đã có dữ liệu "
                        f"(broll={new_brolls}, voice={new_voices}).{usage_hint}"
                    )

            cursor.execute("UPDATE projects SET name = ? WHERE id = ?", (new_name, old_id))

            # Đồng bộ mapping danh sách project theo profile/pid ngay khi đổi tên.
            if profile_name and project_pid:
                cursor.execute(
                    "UPDATE app_projects SET project_name = ? WHERE profile_name = ? AND project_pid = ?",
                    (new_name, str(profile_name), str(project_pid)),
                )
            else:
                # Fallback nếu không truyền pid/profile: cập nhật theo tên cũ.
                cursor.execute(
                    "UPDATE app_projects SET project_name = ? WHERE project_name = ?",
                    (new_name, old_name),
                )

            # Đồng bộ log thành phẩm theo tên project để tab quản lý video hiển thị chuẩn.
            cursor.execute(
                "UPDATE rendered_videos SET project_name = ? WHERE project_name = ?",
                (new_name, old_name),
            )

            conn.commit()
            return True, "Đổi tên project và đồng bộ DB thành công."
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

init_db()
