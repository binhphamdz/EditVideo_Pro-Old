import os
import subprocess
import tempfile
from PIL import Image

# Tránh lỗi ở các bản Pillow mới
if not hasattr(Image, 'ANTIALIAS'): 
    Image.ANTIALIAS = Image.Resampling.LANCZOS

class ThumbnailHandler:
    def __init__(self, ui_tab):
        self.ui = ui_tab

    def generate(self, project_id, broll_dir, trash_dir, act_files, tr_files, render_request_id=None):
        if not project_id or project_id not in self.ui.main_app.projects:
            return

        p_data = self.ui.main_app.get_project_data(project_id)
        changed = False
        
        # Đảm bảo data không bị null nếu file JSON bị lỗi
        if not isinstance(p_data.get("trash"), dict): p_data["trash"] = {}
        if not isinstance(p_data.get("videos"), dict): p_data["videos"] = {}

        def process_folder(files_list, target_dir, data_dict):
            nonlocal changed
            thumb_dir = os.path.join(target_dir, ".thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            
            for vid_name in files_list:
                vid_path = os.path.join(target_dir, vid_name)
                thumb_path = os.path.join(thumb_dir, f"{vid_name}.jpg")
                
                if vid_name not in data_dict or not isinstance(data_dict[vid_name], dict):
                    data_dict[vid_name] = {"description": "", "duration": 0.0, "usage_count": 0}
                    changed = True

                current_dur = data_dict[vid_name].get("duration", 0)
                thumb_exists = os.path.exists(thumb_path)

                # ========================================================
                # TRƯỜNG HỢP 1: Đã có ảnh, nhưng mất độ dài 
                # ========================================================
                if thumb_exists and current_dur <= 0:
                    dur = self._get_duration(vid_path)
                    if dur > 0:
                        data_dict[vid_name]["duration"] = round(dur, 1)
                        changed = True

                # ========================================================
                # TRƯỜNG HỢP 2: Mất ảnh hoàn toàn (File mới thêm vào)
                # -> Gọi hàm tạo ảnh bìa 5 khung hình
                # ========================================================
                elif not thumb_exists:
                    dur = self._create_thumb_direct_ffmpeg(vid_path, thumb_path, vid_name)
                    if dur > 0:
                        data_dict[vid_name]["duration"] = round(dur, 1)
                        changed = True

        try:
            # Bắt đầu quét và xử lý 2 thư mục
            process_folder(act_files, broll_dir, p_data["videos"])
            process_folder(tr_files, trash_dir, p_data["trash"])

            # Chỉ lưu 1 lần duy nhất sau khi 4 luồng đã cày xong
            if changed and project_id in self.ui.main_app.projects:
                fresh_data = self.ui.main_app.get_project_data(project_id)
                
                for v_name, v_info in p_data["videos"].items():
                    if v_name in fresh_data.get("videos", {}):
                        fresh_data["videos"][v_name]["duration"] = v_info.get("duration", 0)
                    else:
                        fresh_data["videos"][v_name] = v_info
                        
                for v_name, v_info in p_data["trash"].items():
                    if v_name in fresh_data.get("trash", {}):
                        fresh_data["trash"][v_name]["duration"] = v_info.get("duration", 0)
                    else:
                        fresh_data["trash"][v_name] = v_info
                        
                self.ui.main_app.save_project_data(project_id, fresh_data)
                
        except Exception as e:
            print(f"Lỗi luồng Thumbnail ngầm: {e}")
            
        finally:
            if project_id in self.ui.main_app.projects:
                self.ui.main_app.root.after(
                    0,
                    lambda: self.ui._build_video_rows(
                        project_id,
                        broll_dir,
                        trash_dir,
                        act_files,
                        tr_files,
                        p_data,
                        render_request_id,
                    ),
                )

    # ------------------------------------------------------------------
    # CÁC HÀM XỬ LÝ LÕI BẰNG FFMPEG (ĐÃ TỐI ƯU HÓA CARD ĐỒ HỌA)
    # ------------------------------------------------------------------
    def _get_duration(self, vid_path):
        """ Lấy độ dài video cực nhanh bằng ffprobe """
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', vid_path]
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, creationflags=creation_flags)
            return float(out.decode('utf-8').strip())
        except Exception:
            return 0.0

    def _extract_frame(self, vid_path, t, out_path):
        """ Bốc 1 khung hình bằng CPU (Chậm hơn tí xíu nhưng tỷ lệ thành công 100% với mọi loại video) """
        cmd = [
            'ffmpeg', '-y', 
            '-ss', str(t), 
            '-i', vid_path, 
            '-frames:v', '1', 
            '-q:v', '2', 
            out_path
        ]
        creation_flags = 0x08000000 if os.name == 'nt' else 0
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creation_flags)

    def _create_thumb_direct_ffmpeg(self, vid_path, thumb_path, vid_name):
        """ Tạo ảnh bìa 5 KHUNG HÌNH ghép ngang chuẩn điện ảnh """
        try:
            dur = self._get_duration(vid_path)
            if dur <= 0: return 0.0

            timepoints = [dur * 0.1, dur * 0.3, dur * 0.5, dur * 0.7, dur * 0.9]
            temp_dir = tempfile.gettempdir()
            temp_paths = [os.path.join(temp_dir, f"frame_{i}_{vid_name}.jpg") for i in range(5)]

            # Cắt 5 nhát
            for i, t in enumerate(timepoints):
                self._extract_frame(vid_path, t, temp_paths[i])

            # Kiểm tra xem có cắt thành công tấm nào không
            valid_images = [Image.open(p) for p in temp_paths if os.path.exists(p)]
            if not valid_images: return 0.0 # Lỗi toàn tập thì bỏ qua

            # Lấy kích thước chuẩn từ tấm ảnh thành công đầu tiên
            base_w = 150
            base_h = int(150 * (valid_images[0].height / valid_images[0].width))

            images = []
            for p in temp_paths:
                if os.path.exists(p):
                    img = Image.open(p)
                    # Dùng Resampling tương thích với cả Pillow cũ và mới
                    resample_filter = Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.ANTIALIAS
                    images.append(img.resize((base_w, base_h), resample_filter))
                else:
                    # Nếu có 1 frame lỗi lẻ tẻ, đắp cục đen vào đúng kích thước
                    images.append(Image.new('RGB', (base_w, base_h), color='black'))

            # Ghép ngang
            merged_img = Image.new('RGB', (base_w * 5, base_h))
            for i, img in enumerate(images):
                merged_img.paste(img, (base_w * i, 0))
            
            merged_img.save(thumb_path, quality=85)

            # Dọn rác
            for p in temp_paths:
                if os.path.exists(p): 
                    try: os.remove(p)
                    except: pass

            return dur
        except Exception as e: 
            print(f"Lỗi ghép ảnh 5 khung: {e}")
            return 0.0