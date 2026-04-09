# -*- coding: utf-8 -*-
import sys
import os
import signal
import atexit
from constants import DATA_DIR
from main_window import CongsecGUI
from PyQt5.QtWidgets import QApplication

# Windows上multiprocessing需要保护主模块
# 注意：必须在if __name__ == '__main__'之前调用freeze_support()
if sys.platform == 'win32':
    import multiprocessing
    multiprocessing.freeze_support()

# 导入清理函数
try:
    from worker_threads import cleanup_all_processes
except ImportError:
    cleanup_all_processes = None

def cleanup_on_exit():
    """程序退出时的清理函数"""
    if cleanup_all_processes:
        try:
            cleanup_all_processes()
        except:
            pass

# 注册退出时的清理函数
atexit.register(cleanup_on_exit)

def signal_handler(signum, frame):
    """信号处理器，用于处理非正常关闭"""
    cleanup_on_exit()
    sys.exit(0)

def main():
    # 设置高DPI缩放
    os.environ["QT_DEVICE_PIXEL_RATIO"] = "0"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"
    os.environ["QT_SCALE_FACTOR"] = "1"
    
    # 注册信号处理器（在非Windows系统上）
    if sys.platform != 'win32':
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    app = QApplication(sys.argv)
    
    # 确保数据目录存在
    os.makedirs(DATA_DIR, exist_ok=True)
    
    window = CongsecGUI()
    window.show()
    
    try:
        exit_code = app.exec_()
    finally:
        # 确保在退出前清理所有进程
        cleanup_on_exit()
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
    