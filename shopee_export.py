import os
import re
import json
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from paths import get_active_profile, get_export_dir, get_posted_video_dir
import database

VIDEO_OUTPUT_DIR = ""
POSTED_VIDEO_DIR = ""
CAPTION_HASHTAGS = "#VideohangDoiSong #VideohangLamDep #VideohangTieuDung #shoppevideo #LuotVuiMuaLien #KOLUyTin #VideoHangGiaDung"
PENDING_SHOPEE_STATUSES = ('', 'Chưa chuyển', 'Chưa đăng', 'Sẵn sàng đăng')

def _sync_profile_paths():
    global VIDEO_OUTPUT_DIR, POSTED_VIDEO_DIR
    VIDEO_OUTPUT_DIR = get_export_dir()
    POSTED_VIDEO_DIR = get_posted_video_dir()

def get_video_output_dir():
    _sync_profile_paths()
    return VIDEO_OUTPUT_DIR


def _get_profile_project_ids(profile_name=None):
    profile_name = profile_name or get_active_profile()
    return database.get_project_ids_for_profile(profile_name)

def normalize_shopee_product_link(value):
    text = str(value or "").strip().strip('"\'')
    if not text: return ""

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    clean_links = []
    
    for line in lines:
        part = line.split()[0].strip().strip('"\'')
        try:
            parsed = urlsplit(part)
            if parsed.scheme and parsed.netloc:
                clean_path = parsed.path.rstrip("/") if parsed.path not in ("", "/") else parsed.path
                part = urlunsplit((parsed.scheme, parsed.netloc, clean_path, "", ""))
        except Exception:
            pass

        if "?" in part: part = part.split("?", 1)[0]
        if "#" in part: part = part.split("#", 1)[0]
            
        part = part.rstrip("/")
        if part: clean_links.append(part)
            
    return "\n".join(clean_links)

def normalize_tiktok_product_link(value):
    text = str(value or "").strip().strip('"\'')
    if not text:
        return ""

    # Cho phép nhập thẳng ID sản phẩm TikTok, ví dụ 1729596837777804242.
    if re.fullmatch(r"\d{8,}", text):
        return f"https://www.tiktok.com/view/product/{text}"

    normalized = normalize_shopee_product_link(text)
    if re.fullmatch(r"\d{8,}", normalized):
        return f"https://www.tiktok.com/view/product/{normalized}"
    return normalized

def _build_caption(product_name):
    words = re.findall(r"\S+", str(product_name or "").strip())
    short_name = " ".join(words[:5]).strip()
    if not short_name: return CAPTION_HASHTAGS
    return f"{short_name} {CAPTION_HASHTAGS}"

def _load_project_product_info(proj_dir):
    # DB-only: lấy thông tin dự án qua project_pid (tên thư mục), sau đó đọc bảng projects.
    project_pid = os.path.basename(os.path.normpath(proj_dir))

    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT project_name FROM app_projects WHERE project_pid = ?",
                (project_pid,),
            )
            ap_row = cursor.fetchone()
            if not ap_row:
                return None

            proj_name = ap_row["project_name"]
            cursor.execute(
                """
                SELECT id, product_name, product_links, tiktok_link, shopee_out_of_stock
                FROM projects
                WHERE name = ?
                """,
                (proj_name,),
            )
            row = cursor.fetchone()
            if not row:
                return None
        finally:
            conn.close()

    tiktok_link = normalize_tiktok_product_link(row["tiktok_link"] or "")
    out_of_stock = bool(row["shopee_out_of_stock"])
    if out_of_stock and not tiktok_link:
        return {"out_of_stock": True, "product_name": "", "caption": "", "links": [""] * 6, "tiktok_link": ""}

    product_name = str(row["product_name"] or "").strip() or str(proj_name or "").strip()
    raw_links = []
    try:
        loaded_links = json.loads(row["product_links"] or "[]")
        if isinstance(loaded_links, list):
            raw_links = loaded_links
    except Exception:
        raw_links = []

    links = [normalize_shopee_product_link(item) for item in raw_links[:6]]
    if len(links) < 6:
        links.extend([""] * (6 - len(links)))

    if not any(links) and not tiktok_link:
        return None

    return {
        "out_of_stock": False,
        "project_id": row["id"],
        "project_name": proj_name,
        "product_name": product_name,
        "caption": _build_caption(product_name),
        "links": links,
        "tiktok_link": tiktok_link,
    }

def is_shopee_out_of_stock_project(proj_dir):
    product_info = _load_project_product_info(proj_dir)
    return bool(product_info and product_info.get("out_of_stock"))

def resolve_shopee_video_path(video_name):
    _sync_profile_paths()
    video_name = str(video_name or "").strip()
    candidates = [video_name]

    # Cho job lưu dạng projectId_fileName -> thử cắt prefix để tìm file thật.
    if video_name and video_name[0].isdigit() and "_" in video_name:
        candidates.append(video_name.split("_", 1)[1])

    for name in candidates:
        for folder in (VIDEO_OUTPUT_DIR, POSTED_VIDEO_DIR):
            candidate = os.path.join(folder, name)
            if os.path.exists(candidate):
                return candidate

    return os.path.join(VIDEO_OUTPUT_DIR, candidates[0] if candidates else "")

# ==============================================================
# [BẢN ĐỘ MỚI] GIAO TIẾP 100% VỚI DATABASE (BỎ CSV)
# ==============================================================

def export_rendered_video_to_shopee_files(proj_dir, out_file, config=None, default_status="Chưa đăng"):
    product_info = _load_project_product_info(proj_dir)
    if not product_info or product_info.get("out_of_stock"): return False, ""

    valid_links = [normalize_shopee_product_link(l) for l in product_info["links"] if str(l).strip()]
    final_link_cell = "\n".join(valid_links)
    video_name = os.path.basename(out_file)
    db_proj_id = product_info.get("project_id")

    # ============================================================
    # Bảo vệ insert shopee_jobs với db_lock để tránh race condition
    # ============================================================
    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        
        # [SỬA] Đổi tên file shopee thành project_id_video_name để unique per project
        # Tránh UNIQUE constraint failed khi render cùng tên file từ các project khác nhau
        unique_video_name = f"{db_proj_id}_{video_name}" if db_proj_id else video_name

        # Ghi thẳng vào Database
        cursor.execute('''
            INSERT OR REPLACE INTO shopee_jobs (project_id, video_name, product_name, links, tiktok_link, caption, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (db_proj_id, unique_video_name, product_info["product_name"], final_link_cell, product_info.get("tiktok_link", ""), product_info["caption"], default_status))
        
        conn.commit()
        conn.close()
    
    return True, "database"

def upsert_manual_tiktok_job(file_path, project_name, tiktok_link, profile_name=None, default_status="Sẵn sàng đăng"):
    file_path = os.path.normpath(str(file_path or "").strip())
    project_name = str(project_name or "").strip()
    tiktok_link = normalize_tiktok_product_link(tiktok_link)
    if not file_path or not project_name or not tiktok_link:
        return None

    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT id, product_name FROM projects WHERE name = ?", (project_name,))
            project = cursor.fetchone()
            if not project:
                return None

            project_id = project["id"]
            project_ids = _get_profile_project_ids(profile_name)
            if project_ids and project_id not in project_ids:
                return None

            product_name = str(project["product_name"] or project_name).strip()
            video_name = os.path.basename(file_path)
            unique_video_name = f"{project_id}_{video_name}"
            caption = project_name

            cursor.execute(
                """
                INSERT INTO shopee_jobs (project_id, video_name, product_name, links, tiktok_link, caption, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_name) DO UPDATE SET
                    project_id = excluded.project_id,
                    product_name = excluded.product_name,
                    tiktok_link = excluded.tiktok_link,
                    caption = excluded.caption,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, unique_video_name, product_name, "", tiktok_link, caption, default_status),
            )
            cursor.execute(
                "UPDATE rendered_videos SET tiktok_link = ? WHERE file_path = ?",
                (tiktok_link, file_path),
            )
            conn.commit()
            return {
                "video_name": unique_video_name,
                "product_name": product_name,
                "tiktok_link": tiktok_link,
                "caption": caption,
                "status": default_status,
            }
        finally:
            conn.close()

def load_shopee_jobs(csv_path=None, config=None, profile_name=None):
    project_ids = _get_profile_project_ids(profile_name)
    if not project_ids:
        return []

    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(project_ids))
        cursor.execute(
            f"""
            SELECT sj.*, p.name AS project_name,
                   COALESCE(NULLIF(sj.tiktok_link, ''), p.tiktok_link, '') AS effective_tiktok_link
            FROM shopee_jobs sj
            LEFT JOIN projects p ON p.id = sj.project_id
            WHERE sj.project_id IN ({placeholders})
            ORDER BY sj.id ASC
            """,
            project_ids,
        )
        rows = cursor.fetchall()
        conn.close()
    
    jobs = []
    for r in rows:
        jobs.append({
            "stt": r['id'],
            "project_name": r['project_name'] if 'project_name' in r.keys() else "",
            "video_name": r['video_name'],
            "product_name": r['product_name'],
            "link": r['links'],
            "tiktok_link": r['effective_tiktok_link'] if 'effective_tiktok_link' in r.keys() else (r['tiktok_link'] if 'tiktok_link' in r.keys() else ""),
            "caption": r['caption'],
            "status": r['status']
        })
    return jobs

def claim_next_shopee_job(worker_label, csv_path=None, config=None, profile_name=None):
    project_ids = _get_profile_project_ids(profile_name)
    if not project_ids:
        return None

    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(PENDING_SHOPEE_STATUSES))
        proj_placeholders = ",".join(["?"] * len(project_ids))
        query = f"""
        SELECT sj.*, p.name AS project_name,
               COALESCE(NULLIF(sj.tiktok_link, ''), p.tiktok_link, '') AS effective_tiktok_link
        FROM shopee_jobs sj
        LEFT JOIN projects p ON p.id = sj.project_id
        WHERE sj.project_id IN ({proj_placeholders}) AND sj.status IN ({placeholders})
        ORDER BY sj.id ASC
        LIMIT 1
        """
        cursor.execute(query, project_ids + list(PENDING_SHOPEE_STATUSES))
        job = cursor.fetchone()
        
        if job:
            job_dict = dict(job)
            new_status = f"Đang xử ({worker_label})"
            cursor.execute("UPDATE shopee_jobs SET status = ?, device_id = ? WHERE id = ?", (new_status, worker_label, job_dict['id']))
            conn.commit()
            conn.close()
            return {
                "stt": job_dict['id'],
                "project_name": job_dict.get('project_name', ''),
                "video_name": job_dict['video_name'],
                "product_name": job_dict['product_name'],
                "link": job_dict['links'],
                "tiktok_link": job_dict.get('effective_tiktok_link') or job_dict.get('tiktok_link', ''),
                "caption": job_dict['caption'],
                "status": new_status,
            }
        conn.close()
    return None

def update_shopee_status(video_name, new_status, csv_path=None, config=None, profile_name=None):
    project_ids = _get_profile_project_ids(profile_name)
    if not project_ids:
        return False

    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        proj_placeholders = ",".join(["?"] * len(project_ids))
        # Nếu video_name có prefix project_id_ (từ tab11_auto_post), dùng exact match
        # Nếu không (từ tab4), tìm pattern %_video_name
        if "_" in video_name and video_name[0].isdigit():
            # Có prefix, dùng exact match
            cursor.execute(
                f"UPDATE shopee_jobs SET status = ? WHERE video_name = ? AND project_id IN ({proj_placeholders})",
                [new_status, video_name] + project_ids,
            )
        else:
            # Không có prefix, tìm pattern
            cursor.execute(
                f"UPDATE shopee_jobs SET status = ? WHERE video_name LIKE ? AND project_id IN ({proj_placeholders})",
                [new_status, f"%_{video_name}"] + project_ids,
            )
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
    return updated

def delete_shopee_jobs(video_names, csv_path=None, config=None, profile_name=None):
    if isinstance(video_names, str): video_names = [video_names]
    if not video_names: return 0

    project_names = set(database.get_project_names_for_profile(profile_name or get_active_profile()))
    if not project_names:
        return 0
    
    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        deleted_count = 0
        
        # [SỬA] Lấy project_id từ rendered_videos, rồi delete shopee_jobs
        # để tránh xóa nhầm job từ project khác cùng tên file
        for video_name in video_names:
            # Tìm project_name từ rendered_videos
            cursor.execute(
                "SELECT project_name FROM rendered_videos WHERE file_path LIKE ?",
                (f"%{video_name}",)
            )
            row = cursor.fetchone()
            if row:
                project_name = row['project_name']
                if project_name not in project_names:
                    continue
                # Query project_id
                cursor.execute("SELECT id FROM projects WHERE name = ?", (project_name,))
                proj_row = cursor.fetchone()
                if proj_row:
                    proj_id = proj_row['id']
                    # Xóa shopee_jobs dùng project_id + video_name pattern
                    cursor.execute(
                        "DELETE FROM shopee_jobs WHERE video_name LIKE ? AND project_id = ?",
                        (f"{proj_id}_{video_name}", proj_id)
                    )
                    deleted_count += cursor.rowcount
        
        conn.commit()
        conn.close()
    return deleted_count

def delete_shopee_jobs_by_names(video_names, profile_name=None):
    if isinstance(video_names, str):
        video_names = [video_names]
    if not video_names:
        return 0

    project_ids = _get_profile_project_ids(profile_name)
    if not project_ids:
        return 0

    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        deleted_count = 0
        proj_placeholders = ",".join(["?"] * len(project_ids))

        for video_name in video_names:
            name = str(video_name or "").strip()
            if not name:
                continue
            cursor.execute(
                f"DELETE FROM shopee_jobs WHERE video_name = ? AND project_id IN ({proj_placeholders})",
                [name] + project_ids,
            )
            deleted_count += cursor.rowcount

        conn.commit()
        conn.close()

    return deleted_count
