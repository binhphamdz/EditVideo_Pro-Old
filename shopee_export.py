import csv
import json
import os
import re
import threading
import unicodedata

from paths import BASE_PATH


WORKSPACE_DIR = os.path.join(BASE_PATH, "Workspace_Data")
VIDEO_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "Kho_Video_Xuat_Xuong")
POSTED_VIDEO_DIR = os.path.join(VIDEO_OUTPUT_DIR, "DA_DANG")
DEFAULT_SHOPEE_EXPORT_CSV = os.path.join(WORKSPACE_DIR, "Danh_sach_video_Shopee.csv")
SHOPEE_HEADERS = ["STT", "Tên Video", "Tên Sản Phẩm", "Link shoppe", "Caption", "Trạng thái"]
PENDING_SHOPEE_STATUSES = {"", "Chưa chuyển", "Chưa đăng", "Sẵn sàng đăng"}
CAPTION_HASHTAGS = "#VideohangDoiSong #VideohangLamDep #VideohangTieuDung #shoppevideo #LuotVuiMuaLien #KOLUyTin #VideoHangGiaDung"

_export_lock = threading.Lock()


def get_shopee_csv_path(config=None):
    configured_path = ""
    if isinstance(config, dict):
        configured_path = str(config.get("shopee_csv_path", "") or "").strip()

    if configured_path:
        return os.path.abspath(os.path.expanduser(configured_path))
    return DEFAULT_SHOPEE_EXPORT_CSV


def _normalize_header(value):
    text = str(value or "").strip().lower()
    normalized = unicodedata.normalize("NFD", text)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized


def _get_column_map(headers):
    normalized_headers = [_normalize_header(item) for item in headers]

    def find_index(candidates, fallback):
        normalized_candidates = {_normalize_header(item) for item in candidates}
        for index, header in enumerate(normalized_headers, start=1):
            if header in normalized_candidates:
                return index
        return fallback

    return {
        "stt": find_index(["STT"], 1),
        "video": find_index(["Tên Video", "Video"], 2),
        "product": find_index(["Tên Sản Phẩm", "Tên sản phẩm"], 3),
        "link": find_index(["Link shoppe", "Link shopee", "Links", "Link"], 4),
        "caption": find_index(["Caption", "Mô tả", "Mo ta"], 5),
        "status": find_index(["Trạng thái", "Trang thai", "Status"], 6),
    }


def _load_project_product_info(proj_dir):
    project_data_path = os.path.join(proj_dir, "project_data.json")
    if not os.path.exists(project_data_path):
        return None

    try:
        with open(project_data_path, "r", encoding="utf-8") as handle:
            project_data = json.load(handle)
    except Exception:
        return None

    product_name = str(project_data.get("product_name", "") or "").strip()
    raw_links = project_data.get("product_links", [])
    if not isinstance(raw_links, list):
        raw_links = []

    links = [str(item or "").strip() for item in raw_links[:6]]
    if len(links) < 6:
        links.extend([""] * (6 - len(links)))

    if not product_name or not any(links):
        return None

    return {
        "product_name": product_name,
        "caption": _build_caption(product_name),
        "links": links,
    }


def _build_caption(product_name):
    words = re.findall(r"\S+", str(product_name or "").strip())
    short_name = " ".join(words[:5]).strip()
    if not short_name:
        return CAPTION_HASHTAGS
    return f"{short_name} {CAPTION_HASHTAGS}"


def _build_link_cell(links):
    cleaned_links = [str(item or "").strip() for item in links[:6]]
    if len(cleaned_links) < 6:
        cleaned_links.extend([""] * (6 - len(cleaned_links)))
    return "\n".join(cleaned_links)


def _ensure_csv_file(csv_path):
    folder = os.path.dirname(csv_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(SHOPEE_HEADERS)


def _read_csv_rows(csv_path):
    if not os.path.exists(csv_path):
        return [SHOPEE_HEADERS.copy()]

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        return [SHOPEE_HEADERS.copy()]

    expected = [_normalize_header(item) for item in SHOPEE_HEADERS]
    actual = [_normalize_header(item) for item in rows[0][: len(SHOPEE_HEADERS)]]
    if actual != expected:
        rows[0] = SHOPEE_HEADERS.copy()
    return rows


def _write_csv_rows(csv_path, rows):
    folder = os.path.dirname(csv_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def _next_stt(rows):
    if len(rows) <= 1:
        return 1
    return len(rows)


def _update_csv_status(csv_path, video_name, new_status):
    if not os.path.exists(csv_path):
        return False

    rows = _read_csv_rows(csv_path)
    if not rows:
        return False

    header = rows[0]
    col_map = _get_column_map(header)
    video_idx = col_map["video"] - 1
    status_idx = col_map["status"] - 1
    updated = False

    for row in rows[1:]:
        while len(row) <= status_idx:
            row.append("")
        if len(row) > video_idx and str(row[video_idx]).strip() == video_name:
            row[status_idx] = new_status
            updated = True

    if updated:
        _write_csv_rows(csv_path, rows)
    return updated


def update_shopee_status(video_name, new_status, csv_path=None, config=None):
    target_csv = csv_path or get_shopee_csv_path(config)
    with _export_lock:
        return _update_csv_status(target_csv, video_name, new_status)


def load_shopee_jobs(csv_path=None, config=None):
    target_csv = csv_path or get_shopee_csv_path(config)
    if not os.path.exists(target_csv):
        return []

    with _export_lock:
        rows = _read_csv_rows(target_csv)
        headers = rows[0]
        col_map = _get_column_map(headers)
        jobs = []
        for row_idx, row in enumerate(rows[1:], start=2):
            while len(row) < len(SHOPEE_HEADERS):
                row.append("")
            video_name = str(row[col_map["video"] - 1] or "").strip()
            if not video_name:
                continue
            jobs.append(
                {
                    "row_index": row_idx,
                    "stt": row[col_map["stt"] - 1],
                    "video_name": video_name,
                    "product_name": str(row[col_map["product"] - 1] or "").strip(),
                    "link": str(row[col_map["link"] - 1] or ""),
                    "caption": str(row[col_map["caption"] - 1] or ""),
                    "status": str(row[col_map["status"] - 1] or "").strip(),
                }
            )
        return jobs


def claim_next_shopee_job(worker_label, csv_path=None, config=None):
    target_csv = csv_path or get_shopee_csv_path(config)
    if not os.path.exists(target_csv):
        return None

    with _export_lock:
        rows = _read_csv_rows(target_csv)
        headers = rows[0]
        col_map = _get_column_map(headers)

        for row_idx, row in enumerate(rows[1:], start=2):
            while len(row) < len(SHOPEE_HEADERS):
                row.append("")
            video_name = str(row[col_map["video"] - 1] or "").strip()
            status = str(row[col_map["status"] - 1] or "").strip()
            if not video_name or status not in PENDING_SHOPEE_STATUSES:
                continue

            processing_status = f"Đang xử ({worker_label})"
            row[col_map["status"] - 1] = processing_status
            _write_csv_rows(target_csv, rows)
            return {
                "row_index": row_idx,
                "stt": row[col_map["stt"] - 1],
                "video_name": video_name,
                "product_name": str(row[col_map["product"] - 1] or "").strip(),
                "link": str(row[col_map["link"] - 1] or ""),
                "caption": str(row[col_map["caption"] - 1] or ""),
                "status": processing_status,
            }

    return None


def resolve_shopee_video_path(video_name):
    for folder in (VIDEO_OUTPUT_DIR, POSTED_VIDEO_DIR):
        candidate = os.path.join(folder, video_name)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(VIDEO_OUTPUT_DIR, video_name)


def export_rendered_video_to_shopee_files(proj_dir, out_file, config=None, default_status="Chưa chuyển"):
    product_info = _load_project_product_info(proj_dir)
    if not product_info:
        return False, ""

    target_csv = get_shopee_csv_path(config)
    link_cell = _build_link_cell(product_info["links"])

    with _export_lock:
        _ensure_csv_file(target_csv)
        rows = _read_csv_rows(target_csv)
        stt_value = _next_stt(rows)
        rows.append(
            [
                stt_value,
                os.path.basename(out_file),
                product_info["product_name"],
                link_cell,
                product_info["caption"],
                default_status,
            ]
        )
        _write_csv_rows(target_csv, rows)

    return True, target_csv
