import sys
import os

def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối cho tài nguyên bên trong file EXE """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_executable_path():
    """ Lấy đường dẫn thư mục chứa file EXE bên ngoài """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.getcwd()

# Biến trung lập cho cả hệ thống
BASE_PATH = get_executable_path()