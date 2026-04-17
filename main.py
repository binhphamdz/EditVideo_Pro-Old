import os
import json
import threading
import time
import tkinter as tk
from tkinter import ttk
import telebot # THƯ VIỆN TELEGRAM BOT
import sys
from paths import BASE_PATH, resource_path

# =================================================================
# [MỚI] BỘ CÔNG CỤ LA BÀN TÌM ĐƯỜNG DẪN DÀNH CHO BẢN BUILD ONEFILE
# =================================================================
def resource_path(relative_path):
    """ Lấy đường dẫn tới các file ĐÍNH KÈM (như logo.png, whoosh.MP3) nằm BÊN TRONG file .exe """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_executable_path():
    """ Lấy đường dẫn thư mục chứa phần mềm (BÊN NGOÀI file .exe) để lưu Data, Config """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.getcwd()

# Dùng biến này làm mỏ neo thay cho os.getcwd()
BASE_PATH = get_executable_path()
# =================================================================

# =================================================================
# BÙA CHỐNG SPAM LỖI WINERROR 6 CỦA MOVIEPY KHI TẮT APP
# =================================================================
import moviepy.video.io.ffmpeg_reader as ffmpeg_reader
old_del = ffmpeg_reader.FFMPEG_VideoReader.__del__
def safe_del(self):
    try:
        old_del(self)
    except Exception:
        pass
ffmpeg_reader.FFMPEG_VideoReader.__del__ = safe_del
# =================================================================

# from tab0_capcut import CapCutTab
from tab1_broll import BRollTab
from tab2_modules import FacelessTab
from tab4_manager import ManagerTab
from tab5_tiktok import TikTokTab
from tab6_subtitle import SubtitleTab  
from tab7_script import ScriptTab  
from tab8_telegram import TelegramTab # <--- IMPORT TAB 8 MỚI
from bot_telegram import TelegramBotManager
from tab9_script_analysis import ScriptAnalysisTab
from tab10_config import ConfigTab

# [ĐÃ SỬA] DÙNG BASE_PATH ĐỂ TẠO THƯ MỤC CẠNH FILE EXE CHỨ KHÔNG PHẢI TRONG TEMP
WORKSPACE_DIR = os.path.join(BASE_PATH, "Workspace_Data")
os.makedirs(WORKSPACE_DIR, exist_ok=True)
PROJECTS_LIST_FILE = os.path.join(WORKSPACE_DIR, "projects_list.json")

GLOBAL_OUT_DIR = os.path.join(WORKSPACE_DIR, "Kho_Video_Xuat_Xuong")
os.makedirs(GLOBAL_OUT_DIR, exist_ok=True)
EXCEL_LOG_FILE = os.path.join(WORKSPACE_DIR, "Danh_Sach_Video.csv")

if not os.path.exists(EXCEL_LOG_FILE):
    with open(EXCEL_LOG_FILE, 'w', encoding='utf-8-sig') as f:
        f.write("Ngày Tạo,Tên Project,Tên Voice,Đường Dẫn Video,Trạng Thái\n")

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 TOOL EDIT VIDEO PRO BY PHẠM VĂN BÌNH - 0345.26.22.29")
        self.root.geometry("1900x1200")
        self.root.configure(bg="#f4f6f9")
        
        # =======================================================
        # [GẮN Ổ KHÓA TỔNG] - LINH HỒN CỦA HỆ THỐNG ĐA LUỒNG
        # =======================================================
        self.json_lock = threading.Lock()
        
        # =======================================================
        # GẮN ICON SỬ DỤNG HÀM LA BÀN
        # =======================================================
        try:
            icon_path = resource_path("icon.png")
            icon_image = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, icon_image)
        except Exception as e:
            print("Chưa tìm thấy file logo.png: ", e)
        # =======================================================
        
        self.config = self.load_config()
        self.projects = self.load_projects()
        
        # Các biến quản lý Bot Telegram
        self.bot = None
        self.bot_is_running = False
        
        self.setup_ui()
        
        
    def get_proj_dir(self, pid):
        p_dir = os.path.join(WORKSPACE_DIR, pid)
        os.makedirs(p_dir, exist_ok=True)
        return p_dir

    def load_config(self):
        conf_file = os.path.join(BASE_PATH, "config_dao_dien.json")
        try:
            with open(conf_file, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}

    def save_config(self):
        conf_file = os.path.join(BASE_PATH, "config_dao_dien.json")
        try:
            with open(conf_file, "w", encoding="utf-8") as f: json.dump(self.config, f, indent=4)
        except: pass

    def load_projects(self):
        try:
            with open(PROJECTS_LIST_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}

    # =======================================================
    # [NÂNG CẤP 1] - LƯU PROJECT CÓ BACKUP VÀ Ổ KHÓA
    # =======================================================
    def save_projects(self):
        import shutil
        backup_file = PROJECTS_LIST_FILE.replace(".json", "_backup.json")
        
        with self.json_lock: # Bật khóa an toàn
            # 1. Tạo file Backup
            if os.path.exists(PROJECTS_LIST_FILE) and os.path.getsize(PROJECTS_LIST_FILE) > 0:
                try: shutil.copy2(PROJECTS_LIST_FILE, backup_file)
                except: pass
            
            # 2. Ghi file chính
            try:
                with open(PROJECTS_LIST_FILE, "w", encoding="utf-8") as f: 
                    json.dump(self.projects, f, indent=4)
            except: pass

    # =======================================================
    # [NÂNG CẤP 2] - ĐỌC DATA CŨNG PHẢI ĐÓNG KHÓA (CHỐNG MẤT ĐIỂM)
    # =======================================================
    def get_project_data(self, pid):
        data_file = os.path.join(self.get_proj_dir(pid), "project_data.json")
        backup_file = os.path.join(self.get_proj_dir(pid), "project_data_backup.json")
        
        with self.json_lock: # Khóa lại không cho ai ghi lúc mình đang đọc
            # 1. Thử đọc file chính trước
            if os.path.exists(data_file):
                try:
                    with open(data_file, 'r', encoding='utf-8') as f: 
                        return json.load(f)
                except Exception as e:
                    print(f"⚠️ Cảnh báo: File dự án chính bị hỏng ({e}). Đang kích hoạt Backup...")
                    
                    # 2. Nếu file chính hỏng (do sập nguồn), lôi file Backup ra xài
                    if os.path.exists(backup_file):
                        try:
                            with open(backup_file, 'r', encoding='utf-8') as f: 
                                data = json.load(f)
                                
                                # Khôi phục đè ngược lại file chính luôn
                                with open(data_file, 'w', encoding='utf-8') as f_recover:
                                    json.dump(data, f_recover, indent=4)
                                return data
                        except: pass

        return {"videos": {}, "trash": {}, "timeline": []}

    # =======================================================
    # [NÂNG CẤP 3] - GHI DATA CHÍNH CHU TRỌN BỘ Ổ KHÓA + BACKUP
    # =======================================================
    def save_project_data(self, pid, data):
        import shutil
        data_file = os.path.join(self.get_proj_dir(pid), "project_data.json")
        backup_file = os.path.join(self.get_proj_dir(pid), "project_data_backup.json")
        
        with self.json_lock: # Bật khóa an toàn
            # 1. TẠO FILE BACKUP
            if os.path.exists(data_file) and os.path.getsize(data_file) > 0:
                try:
                    shutil.copy2(data_file, backup_file)
                except:
                    pass
                    
            # 2. GHI ĐÈ FILE CHÍNH
            try:
                with open(data_file, 'w', encoding='utf-8') as f: 
                    json.dump(data, f, indent=4)
            except Exception as e:
                print(f"Lỗi khi lưu data: {e}")

    def setup_ui(self):
        # ... (Từ đoạn này sếp giữ nguyên code cũ của sếp nhé) ...
        style = ttk.Style()
        style.theme_use("clam")
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.frame_tab1 = tk.Frame(self.notebook, bg="#f4f6f9")
        self.frame_tab2 = tk.Frame(self.notebook, bg="#f4f6f9")
        self.frame_tab4 = tk.Frame(self.notebook, bg="#f4f6f9") 
        
        self.notebook.add(self.frame_tab1, text=" 📂KHO CẢNH TRÁM ")
        self.notebook.add(self.frame_tab2, text=" 🚀 EDIT VIDEO ĐA LUỒNG ")
        self.notebook.add(self.frame_tab4, text=" 📊 QUẢN LÝ VIDEO ")
        
        self.tab1 = BRollTab(self.frame_tab1, self)
        self.tab2 = FacelessTab(self.frame_tab2, self)
        self.tab4 = ManagerTab(self.frame_tab4, self) 

        self.tab5_frame = tk.Frame(self.notebook, bg="#f4f6f9")
        self.notebook.add(self.tab5_frame, text=" 🎵 TẢI VIDEO TIK TOK ")
        self.tab5 = TikTokTab(self.tab5_frame, self)

        self.tab7_frame = tk.Frame(self.notebook, bg="#f4f6f9")
        self.notebook.add(self.tab7_frame, text="🍲 XÀO KỊCH BẢN")
        self.tab7 = ScriptTab(self.tab7_frame, self)

   

        # Thêm khung cho Tab 9
        self.tab9_frame = tk.Frame(self.notebook, bg="#f4f6f9")
        self.notebook.add(self.tab9_frame, text=" 🔪 GHÉP KỊCH BẢN ")
        self.tab9 = ScriptAnalysisTab(self.tab9_frame, self)

             # TAB 8: TELEGRAM BOT
        self.tab8_frame = tk.Frame(self.notebook, bg="#f4f6f9")
        self.notebook.add(self.tab8_frame, text=" 🤖CẤU HÌNH BOT TELEGRAM ")
        self.tab8 = TelegramTab(self.tab8_frame, self)

        # [THÊM TAB 10 VÀO ĐÂY]
        self.tab10_frame = tk.Frame(self.notebook, bg="#f4f6f9")
        self.notebook.add(self.tab10_frame, text=" ⚙️CẤU HÌNH HỆ THỐNG ")
        self.tab10 = ConfigTab(self.tab10_frame, self)




        # Khởi tạo Quản lý Bot
        self.telegram_manager = TelegramBotManager(self)
        self.telegram_manager.start_telegram_bot()

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def on_tab_changed(self, event):
        self.tab2.update_combo_projects()
        self.tab1.refresh_project_list()
        self.tab4.load_excel_data() 

    # =================================================================
    # HÀM CẦU NỐI (PROXY) TỪ TAB 8 SANG BOT MANAGER
    # =================================================================
    def restart_telegram_bot(self):
        """Hàm này được gọi từ Tab 8 khi bác bấm 'Lưu & Khởi Động' """
        if hasattr(self, 'telegram_manager') and self.telegram_manager:
            self.telegram_manager.stop_telegram_bot()
            import time
            time.sleep(1) 
            self.telegram_manager.start_telegram_bot()
        
    def stop_telegram_bot(self):
        """Hàm này được gọi từ Tab 8 khi bác bấm 'Tắt Bot' """
        if hasattr(self, 'telegram_manager') and self.telegram_manager:
            self.telegram_manager.stop_telegram_bot()

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()