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

    # [MIGRATION] Lưu timeline vào DB thay cho project_data.json
    try:
        cursor.execute("ALTER TABLE projects ADD COLUMN timeline_json TEXT DEFAULT '[]'")
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
        "shopee_out_of_stock": False,
        "product_links": ["", "", "", "", "", ""],
        "ref_img_1": "",
        "ref_img_2": "",
        "voice_usage": {},
        "voice_srt_cache": {},
    }

    with db_lock:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, product_name, product_context, ref_img_1, ref_img_2,
                       product_links, shopee_out_of_stock, timeline_json
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
                "SELECT file_name, usage_count, srt_cache FROM voices WHERE project_id = ?",
                (db_proj_id,),
            )
            for row in cursor.fetchall():
                payload["voice_usage"][row["file_name"]] = int(row["usage_count"] or 0)
                if row["srt_cache"]:
                    payload["voice_srt_cache"][row["file_name"]] = row["srt_cache"]

            cursor.execute(
                "SELECT file_name, duration, description, usage_count, keep_audio, status FROM brolls WHERE project_id = ?",
                (db_proj_id,),
            )
            for row in cursor.fetchall():
                item = {
                    "duration": float(row["duration"] or 0),
                    "description": row["description"] or "",
                    "usage_count": int(row["usage_count"] or 0),
                    "keep_audio": bool(row["keep_audio"]),
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
                    1 if payload.get("shopee_out_of_stock", False) else 0,
                    project_status or "active",
                    json.dumps(payload.get("timeline", []), ensure_ascii=False),
                    db_proj_id,
                ),
            )

            # Voices: upsert usage + srt, giữ nguyên last_used/status đã có.
            voice_usage = payload.get("voice_usage", {}) or {}
            voice_srt = payload.get("voice_srt_cache", {}) or {}

            cursor.execute(
                "SELECT file_name, last_used, status FROM voices WHERE project_id = ?",
                (db_proj_id,),
            )
            existing_voice_meta = {r["file_name"]: (r["last_used"], r["status"] or "active") for r in cursor.fetchall()}

            all_voice_names = set(voice_usage.keys()) | set(voice_srt.keys())
            for file_name in all_voice_names:
                last_used, status = existing_voice_meta.get(file_name, (None, "active"))
                cursor.execute(
                    """
                    INSERT INTO voices (project_id, file_name, usage_count, srt_cache, last_used, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, file_name) DO UPDATE SET
                        usage_count = excluded.usage_count,
                        srt_cache = excluded.srt_cache
                    """,
                    (
                        db_proj_id,
                        file_name,
                        int(voice_usage.get(file_name, 0) or 0),
                        str(voice_srt.get(file_name, "") or ""),
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
                    INSERT INTO brolls (project_id, file_name, duration, description, usage_count, keep_audio, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'active')
                    ON CONFLICT(project_id, file_name) DO UPDATE SET
                        duration = excluded.duration,
                        description = excluded.description,
                        usage_count = excluded.usage_count,
                        keep_audio = excluded.keep_audio,
                        status = 'active'
                    """,
                    (
                        db_proj_id,
                        file_name,
                        float(info.get("duration", 0) or 0),
                        str(info.get("description", "") or ""),
                        int(info.get("usage_count", 0) or 0),
                        1 if info.get("keep_audio", False) else 0,
                    ),
                )

            for file_name, info in trash.items():
                info = info or {}
                cursor.execute(
                    """
                    INSERT INTO brolls (project_id, file_name, duration, description, usage_count, keep_audio, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'trash')
                    ON CONFLICT(project_id, file_name) DO UPDATE SET
                        duration = excluded.duration,
                        description = excluded.description,
                        usage_count = excluded.usage_count,
                        keep_audio = excluded.keep_audio,
                        status = 'trash'
                    """,
                    (
                        db_proj_id,
                        file_name,
                        float(info.get("duration", 0) or 0),
                        str(info.get("description", "") or ""),
                        int(info.get("usage_count", 0) or 0),
                        1 if info.get("keep_audio", False) else 0,
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