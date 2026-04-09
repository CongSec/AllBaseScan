# -*- coding: utf-8 -*-
# 常量定义模块
import multiprocessing

# 路径配置
CONFIG_FILE_PATH = "config.json"
DATA_DIR = "data"

# 性能阈值
CHUNK_SIZE = 2 * 1024 * 1024  # 2MB - 增大块大小以提升IO性能
LARGE_FILE_THRESHOLD = 10 * 1024 * 1024  # 10MB - 超过此大小使用流式处理
STREAMING_LINE_PROGRESS_INTERVAL = 5000  # 流式处理时每处理多少行报告一次进度（提高以减少UI更新频率）
# 分页显示配置（用于树形视图）
FILES_PER_PAGE = 100  # 每页显示的文件数
MATCHES_PER_FILE_PER_PAGE = 50  # 每个文件每页显示的匹配项数
MAX_RESULTS_TREE = 5000
MAX_CONTENT_LENGTH = 1000  # 限制树形视图中显示的内容长度
# 保留旧常量名以兼容（已废弃，使用分页功能）
MAX_FILES_TREE = FILES_PER_PAGE
MAX_MATCHES_PER_FILE_TREE = MATCHES_PER_FILE_PER_PAGE

# 并发配置
CPU_COUNT = multiprocessing.cpu_count()
# 限制最大进程数，避免在高核数CPU上创建过多进程导致系统卡死和孤儿进程
# 经验值：超过12个进程后，上下文切换开销会显著增加，性能反而下降
# 在Windows上，spawn模式创建进程开销更大，需要更保守的限制
MAX_WORKER_PROCESSES = min(max(1, CPU_COUNT - 1), 12)  # 最多12个进程，避免过多进程导致系统资源耗尽
DEFAULT_WORKER_PROCESSES = min(MAX_WORKER_PROCESSES, 8)  # 默认最多8个进程，避免过多进程导致上下文切换开销