import os
import re
import json
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from paths import get_export_dir, get_posted_video_dir
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

def _build_caption(product_name):
    words = re.findall(r"\S+", str(product_name or "").strip())
    short_name = " ".join(words[:5]).strip()
    if not short_name: return CAPTION_HASHTAGS
    return f"{short_name} {CAPTION_HASHTAGS}"

def _load_project_product_info(proj_dir):
    project_data_path = os.path.join(proj_dir, "project_data.json")
    if not os.path.exists(project_data_path): return None

    try:
        with open(project_data_path, "r", encoding="utf-8") as handle:
            project_data = json.load(handle)
    except Exception: return None

    out_of_stock = bool(project_data.get("shopee_out_of_stock", False))
    if out_of_stock:
        return {"out_of_stock": True, "product_name": "", "caption": "", "links": [""] * 6}

    product_name = str(project_data.get("product_name", "") or "").strip()
    raw_links = project_data.get("product_links", [])
    if not isinstance(raw_links, list): raw_links = []

    links = [normalize_shopee_product_link(item) for item in raw_links[:6]]
    if len(links) < 6: links.extend([""] * (6 - len(links)))

    if not product_name or not any(links): return None

    return {
        "out_of_stock": False,
        "product_name": product_name,
        "caption": _build_caption(product_name),
        "links": links,
    }

def is_shopee_out_of_stock_project(proj_dir):
    product_info = _load_project_product_info(proj_dir)
    return bool(product_info and product_info.get("out_of_stock"))

def resolve_shopee_video_path(video_name):
    _sync_profile_paths()
    for folder in (VIDEO_OUTPUT_DIR, POSTED_VIDEO_DIR):
        candidate = os.path.join(folder, video_name)
        if os.path.exists(candidate): return candidate
    return os.path.join(VIDEO_OUTPUT_DIR, video_name)

# ==============================================================
# [BẢN ĐỘ MỚI] GIAO TIẾP 100% VỚI DATABASE (BỎ CSV)
# ==============================================================

def export_rendered_video_to_shopee_files(proj_dir, out_file, config=None, default_status="Chưa đăng"):
    product_info = _load_project_product_info(proj_dir)
    if not product_info or product_info.get("out_of_stock"): return False, ""

    valid_links = [normalize_shopee_product_link(l) for l in product_info["links"] if str(l).strip()]
    final_link_cell = "\n".join(valid_links)
    video_name = os.path.basename(out_file)
    proj_name = os.path.basename(proj_dir)

    # ============================================================
    # Bảo vệ insert shopee_jobs với db_lock để tránh race condition
    # ============================================================
    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        
        # Lấy ID của Project
        cursor.execute("SELECT id FROM projects WHERE name = ?", (proj_name,))
        row = cursor.fetchone()
        db_proj_id = row['id'] if row else None

        # [SỬA] Đổi tên file shopee thành project_id_video_name để unique per project
        # Tránh UNIQUE constraint failed khi render cùng tên file từ các project khác nhau
        unique_video_name = f"{db_proj_id}_{video_name}" if db_proj_id else video_name

        # Ghi thẳng vào Database
        cursor.execute('''
            INSERT OR REPLACE INTO shopee_jobs (project_id, video_name, product_name, links, caption, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (db_proj_id, unique_video_name, product_info["product_name"], final_link_cell, product_info["caption"], default_status))
        
        conn.commit()
        conn.close()
    
    return True, "database"

def load_shopee_jobs(csv_path=None, config=None):
    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shopee_jobs ORDER BY id ASC")
        rows = cursor.fetchall()
        conn.close()
    
    jobs = []
    for r in rows:
        jobs.append({
            "stt": r['id'],
            "video_name": r['video_name'],
            "product_name": r['product_name'],
            "link": r['links'],
            "caption": r['caption'],
            "status": r['status']
        })
    return jobs

def claim_next_shopee_job(worker_label, csv_path=None, config=None):
    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(PENDING_SHOPEE_STATUSES))
        query = f"SELECT * FROM shopee_jobs WHERE status IN ({placeholders}) ORDER BY id ASC LIMIT 1"
        cursor.execute(query, PENDING_SHOPEE_STATUSES)
        job = cursor.fetchone()
        
        if job:
            job_dict = dict(job)
            new_status = f"Đang xử ({worker_label})"
            cursor.execute("UPDATE shopee_jobs SET status = ?, device_id = ? WHERE id = ?", (new_status, worker_label, job_dict['id']))
            conn.commit()
            conn.close()
            return {
                "stt": job_dict['id'],
                "video_name": job_dict['video_name'],
                "product_name": job_dict['product_name'],
                "link": job_dict['links'],
                "caption": job_dict['caption'],
                "status": new_status,
            }
        conn.close()
    return None

def update_shopee_status(video_name, new_status, csv_path=None, config=None):
    with database.db_lock:
        conn = database.get_connection()
        cursor = conn.cursor()
        # Nếu video_name có prefix project_id_ (từ tab11_auto_post), dùng exact match
        # Nếu không (từ tab4), tìm pattern %_video_name
        if "_" in video_name and video_name[0].isdigit():
            # Có prefix, dùng exact match
            cursor.execute("UPDATE shopee_jobs SET status = ? WHERE video_name = ?", (new_status, video_name))
        else:
            # Không có prefix, tìm pattern
            cursor.execute("UPDATE shopee_jobs SET status = ? WHERE video_name LIKE ?", (new_status, f"%_{video_name}"))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
    return updated

def delete_shopee_jobs(video_names, csv_path=None, config=None):
    if isinstance(video_names, str): video_names = [video_names]
    if not video_names: return 0
    
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