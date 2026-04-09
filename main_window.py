# -*- coding: utf-8 -*-
import sys
import os
import re
import csv
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QListWidget, QListWidgetItem, QLabel,
    QSpinBox, QTabWidget, QFileDialog, QMessageBox, QProgressBar,
    QGroupBox, QFrame, QDialog, QDialogButtonBox, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QTextBrowser, QMenu, QAction,
    QPlainTextEdit, QSplitter
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSettings
from PyQt5.QtGui import QTextCharFormat, QColor, QSyntaxHighlighter, QFont

from constants import DATA_DIR, MAX_RESULTS_TREE, DEFAULT_WORKER_PROCESSES, CPU_COUNT
from config_manager import ConfigManager
from text_processor import TextProcessor
from syntax_highlighter import ResultHighlighter
from tree_viewer import TreeResultWindow
from fullscreen_viewer import FullscreenResultWindow
from worker_threads import WorkerThread, cleanup_all_processes
from export_manager import ExportThread
from keyword_dialogs import AddKeywordDialog, EditKeywordDialog

class CongsecGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("CongSec", "TextProcessor")
        self.config = ConfigManager.load_config()
        self.worker_thread = None
        self.current_results = []
        self.result_buffer = []
        # 保存原始结果文本（包含已排除提示），用于在勾选/取消“显示已排除提示”时重新渲染
        self.raw_batch_result_text = ""
        self.raw_realtime_result_text = ""
        self.buffer_timer = QTimer()
        self.buffer_timer.timeout.connect(self.flush_buffer)
        self.tree_result_windows = []  # 结构化查询窗口列表，支持多个窗口
        self.apply_modern_style()
        self.init_ui()

    def apply_modern_style(self):
        """统一设置浅色系风格，提升界面观感"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f7fb;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dfe3ec;
                border-radius: 6px;
                margin-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px 0 4px;
                background-color: #f5f7fb;
                color: #2d2f33;
            }
            QPushButton {
                padding: 6px 12px;
                border-radius: 4px;
                background-color: #4f6bed;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: #3d58d4;
            }
            QPushButton:disabled {
                background-color: #b7c0dd;
                color: #f0f0f0;
            }
            QPlainTextEdit, QTextEdit {
                background: #fbfcff;
                border: 1px solid #dfe3ec;
                border-radius: 4px;
            }
            QListWidget, QTreeWidget {
                border: 1px solid #dfe3ec;
                border-radius: 4px;
                background: #fbfcff;
            }
            QProgressBar {
                border: 1px solid #dfe3ec;
                border-radius: 4px;
                text-align: center;
                color: #2d2f33;
            }
            QTabWidget::pane {
                border: 1px solid #dfe3ec;
                border-radius: 4px;
                background: #ffffff;
            }
        """)

    def init_ui(self):
        self.setWindowTitle("文本批量处理工具 by CongSec~")
        # 恢复窗口大小和位置
        self.restore_geometry()
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        main_layout.addWidget(splitter)

        config_panel = QFrame()
        config_panel.setFrameStyle(QFrame.Box)
        config_panel.setMinimumWidth(260)
        config_panel.setMaximumWidth(360)
        config_layout = QVBoxLayout(config_panel)
        splitter.addWidget(config_panel)

        keyword_group = QGroupBox("关键字列表")
        keyword_layout = QVBoxLayout(keyword_group)
        self.keyword_list = QListWidget()
        self.keyword_list.setAlternatingRowColors(True)
        # 连接勾选状态改变信号，实现记忆功能
        self.keyword_list.itemChanged.connect(self.on_keyword_check_changed)
        self.update_keyword_list()
        keyword_layout.addWidget(self.keyword_list)
        add_keyword_btn = QPushButton("添加关键字")
        add_keyword_btn.clicked.connect(self.add_keyword_dialog)
        keyword_layout.addWidget(add_keyword_btn)
        edit_keyword_btn = QPushButton("编辑选中关键字")
        edit_keyword_btn.clicked.connect(self.edit_keyword_dialog)
        keyword_layout.addWidget(edit_keyword_btn)
        delete_keyword_btn = QPushButton("删除选中关键字")
        delete_keyword_btn.clicked.connect(self.delete_keyword)
        keyword_layout.addWidget(delete_keyword_btn)
        config_layout.addWidget(keyword_group)

        config_group = QGroupBox("默认配置")
        config_group_layout = QVBoxLayout(config_group)
        lines_layout = QHBoxLayout()
        lines_layout.addWidget(QLabel("默认附近行数（-1表示不输出附近行）:"))
        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(-1, 100)  # 允许设置为-1
        self.lines_spin.setValue(self.config["nearby_lines"])
        self.lines_spin.setToolTip("设置为-1时不输出附近行内容，设置为0或正数时输出对应行数的附近内容")
        self.lines_spin.valueChanged.connect(self.update_default_config)
        lines_layout.addWidget(self.lines_spin)
        config_group_layout.addLayout(lines_layout)
        chars_layout = QHBoxLayout()
        chars_layout.addWidget(QLabel("默认附近字符数:"))
        self.chars_spin = QSpinBox()
        self.chars_spin.setRange(0, 1000)
        self.chars_spin.setValue(self.config["nearby_chars"])
        self.chars_spin.valueChanged.connect(self.update_default_config)
        chars_layout.addWidget(self.chars_spin)
        config_group_layout.addLayout(chars_layout)
        down_layout = QHBoxLayout()
        down_layout.addWidget(QLabel("默认向下行数:"))
        self.down_spin = QSpinBox()
        self.down_spin.setRange(-100, 100)
        self.down_spin.setValue(self.config.get("down_lines", 0))
        self.down_spin.valueChanged.connect(self.update_default_config)
        down_layout.addWidget(self.down_spin)
        config_group_layout.addLayout(down_layout)
        up_layout = QHBoxLayout()
        up_layout.addWidget(QLabel("默认向上行数:"))
        self.up_spin = QSpinBox()
        self.up_spin.setRange(-100, 100)
        self.up_spin.setValue(self.config.get("up_lines", 0))
        self.up_spin.valueChanged.connect(self.update_default_config)
        up_layout.addWidget(self.up_spin)
        config_group_layout.addLayout(up_layout)
        self.auto_export_cb = QCheckBox("后台自动导出CSV")
        self.auto_export_cb.setChecked(self.config.get("auto_export", True))
        self.auto_export_cb.toggled.connect(self.toggle_auto_export)
        config_group_layout.addWidget(self.auto_export_cb)
        self.auto_detect_encoding_cb = QCheckBox("自动识别文件编码")
        self.auto_detect_encoding_cb.setChecked(self.config.get("auto_detect_encoding", True))
        self.auto_detect_encoding_cb.toggled.connect(self.toggle_auto_detect_encoding)
        config_group_layout.addWidget(self.auto_detect_encoding_cb)
        workers_layout = QHBoxLayout()
        workers_layout.addWidget(QLabel("并发进程数:"))
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, CPU_COUNT)
        self.workers_spin.setValue(self.config.get("max_workers", DEFAULT_WORKER_PROCESSES))
        self.workers_spin.setToolTip(f"设置并发处理的进程数（1-{CPU_COUNT}），建议设置为CPU核心数-1。更多进程可以提升处理速度，但会占用更多内存。注意：最大进程数已限制为12个，以避免在高核数CPU上导致系统卡死和孤儿进程。")
        self.workers_spin.valueChanged.connect(self.update_worker_processes)
        workers_layout.addWidget(self.workers_spin)
        workers_layout.addWidget(QLabel(f"(CPU核心数: {CPU_COUNT})"))
        config_group_layout.addLayout(workers_layout)
        config_layout.addWidget(config_group)
        
        # 配置管理组
        config_manage_group = QGroupBox("配置管理")
        config_manage_layout = QVBoxLayout(config_manage_group)
        export_config_btn = QPushButton("导出配置")
        export_config_btn.clicked.connect(self.export_config)
        config_manage_layout.addWidget(export_config_btn)
        import_config_btn = QPushButton("导入配置")
        import_config_btn.clicked.connect(self.import_config)
        config_manage_layout.addWidget(import_config_btn)
        config_layout.addWidget(config_manage_group)
        
        config_layout.addStretch()

        right_panel_container = QWidget()
        right_panel = QVBoxLayout(right_panel_container)
        splitter.addWidget(right_panel_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)

        batch_tab = QWidget()
        batch_layout = QVBoxLayout(batch_tab)
        file_group = QGroupBox("文件选择")
        file_layout = QVBoxLayout(file_group)
        select_files_btn = QPushButton("选择文件")
        select_files_btn.clicked.connect(self.select_files)
        file_layout.addWidget(select_files_btn)
        select_folder_btn = QPushButton("选择文件夹(递归)")
        select_folder_btn.clicked.connect(self.select_folder_recursive)
        file_layout.addWidget(select_folder_btn)
        self.selected_files_label = QLabel("未选择文件")
        file_layout.addWidget(self.selected_files_label)
        batch_layout.addWidget(file_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        batch_layout.addWidget(self.progress_bar)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        batch_layout.addWidget(self.progress_label)
        self.show_excluded_cb_batch = QCheckBox("显示已排除提示")
        self.show_excluded_cb_batch.setChecked(False)
        batch_layout.addWidget(self.show_excluded_cb_batch)
        self.process_btn = QPushButton("开始批量处理")
        self.process_btn.clicked.connect(self.start_batch_processing)
        batch_layout.addWidget(self.process_btn)
        self.stop_btn = QPushButton("停止处理")
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setVisible(False)
        batch_layout.addWidget(self.stop_btn)
        self.export_csv_btn = QPushButton("导出结果到CSV")
        self.export_csv_btn.clicked.connect(self.export_to_csv)
        self.export_csv_btn.setVisible(False)
        batch_layout.addWidget(self.export_csv_btn)
        result_group = QGroupBox("匹配结果")
        result_layout = QVBoxLayout(result_group)
        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.highlighter = ResultHighlighter(self.result_text.document())
        monospace_font = QFont("Consolas", 10)
        self.result_text.setFont(monospace_font)
        result_layout.addWidget(self.result_text)
        result_btn_layout = QHBoxLayout()
        fullscreen_batch_btn = QPushButton("全屏查看")
        fullscreen_batch_btn.clicked.connect(self.show_batch_fullscreen)
        result_btn_layout.addWidget(fullscreen_batch_btn)
        tree_view_btn = QPushButton("结构化查看")
        tree_view_btn.clicked.connect(self.show_tree_results)
        result_btn_layout.addWidget(tree_view_btn)
        result_layout.addLayout(result_btn_layout)
        batch_layout.addWidget(result_group)
        self.tab_widget.addTab(batch_tab, "批量处理")

        realtime_tab = QWidget()
        realtime_layout = QVBoxLayout(realtime_tab)
        input_group = QGroupBox("输入文本")
        input_layout = QVBoxLayout(input_group)
        self.input_text = QPlainTextEdit()
        self.input_text.setPlaceholderText("请输入要匹配的文本...")
        self.input_text.setFont(monospace_font)
        input_layout.addWidget(self.input_text)
        self.show_excluded_cb_realtime = QCheckBox("显示已排除提示")
        self.show_excluded_cb_realtime.setChecked(False)
        input_layout.addWidget(self.show_excluded_cb_realtime)
        process_realtime_btn = QPushButton("单个匹配")
        process_realtime_btn.clicked.connect(self.process_realtime)
        input_layout.addWidget(process_realtime_btn)
        realtime_layout.addWidget(input_group)
        result_group_realtime = QGroupBox("匹配结果")
        result_layout_realtime = QVBoxLayout(result_group_realtime)
        self.result_text_realtime = QPlainTextEdit()
        self.result_text_realtime.setReadOnly(True)
        self.result_text_realtime.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.result_text_realtime.setFont(monospace_font)
        self.highlighter_realtime = ResultHighlighter(self.result_text_realtime.document())
        result_layout_realtime.addWidget(self.result_text_realtime)
        fullscreen_realtime_btn = QPushButton("全屏查看")
        fullscreen_realtime_btn.clicked.connect(self.show_realtime_fullscreen)
        result_layout_realtime.addWidget(fullscreen_realtime_btn)
        export_realtime_btn = QPushButton("导出结果到CSV")
        export_realtime_btn.clicked.connect(self.export_realtime_to_csv)
        result_layout_realtime.addWidget(export_realtime_btn)
        realtime_layout.addWidget(result_group_realtime)
        self.tab_widget.addTab(realtime_tab, "单个匹配")

        right_panel.addWidget(self.tab_widget)
        main_layout.addWidget(config_panel)
        main_layout.addLayout(right_panel)

    def update_keyword_list(self):
        # 临时断开信号，避免在更新列表时触发保存
        try:
            self.keyword_list.itemChanged.disconnect()
        except:
            pass
        
        self.keyword_list.clear()
        for kw in self.config["keywords"]:
            words = kw.get("words", [])
            exclude = kw.get("exclude", [])
            lines = kw.get("nearby_lines", self.config["nearby_lines"])
            chars = kw.get("nearby_chars", self.config["nearby_chars"])
            down = kw.get("down_lines", self.config["down_lines"])
            up = kw.get("up_lines", self.config["up_lines"])
            regex = kw.get("use_regex", False)
            remark = kw.get("remark", "").strip()  # 获取备注信息
            
            # 优先显示备注，如果没有备注则显示关键字信息
            if remark:
                # 有备注时，优先显示备注，后面显示关键字信息
                text = f"{remark} [关键字: {'+'.join(words)}]"
            else:
                # 没有备注时，显示原来的格式
                text = f"关键字: {'+'.join(words)} (行:{lines} 字符:{chars} 下:{down} 上:{up})"
            
            if regex:
                text += " | 正则表达式"
            if exclude:
                text += f" | 排除: {'/'.join(exclude)}"
            if kw.get("multi_line_exclude", False):
                text += " | 多行过滤: 是"
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # 从config.json中读取enabled状态（记忆功能）
            item.setCheckState(Qt.Checked if kw.get("enabled", True) else Qt.Unchecked)
            self.keyword_list.addItem(item)
        
        # 重新连接信号
        self.keyword_list.itemChanged.connect(self.on_keyword_check_changed)
    
    def on_keyword_check_changed(self, item):
        """关键字勾选状态改变时的处理函数，保存到config.json"""
        row = self.keyword_list.row(item)
        if row >= 0 and row < len(self.config["keywords"]):
            # 更新config中对应关键字的enabled状态
            is_checked = item.checkState() == Qt.Checked
            self.config["keywords"][row]["enabled"] = is_checked
            # 保存到config.json
            ConfigManager.save_config(self.config)

    def update_default_config(self):
        self.config["nearby_lines"] = self.lines_spin.value()
        self.config["nearby_chars"] = self.chars_spin.value()
        self.config["down_lines"] = self.down_spin.value()
        self.config["up_lines"] = self.up_spin.value()
        ConfigManager.save_config(self.config)
        self.update_keyword_list()

    def toggle_auto_export(self, checked):
        self.config["auto_export"] = checked
        ConfigManager.save_config(self.config)

    def toggle_auto_detect_encoding(self, checked):
        self.config["auto_detect_encoding"] = checked
        ConfigManager.save_config(self.config)
    
    def update_worker_processes(self, value):
        self.config["max_workers"] = value
        ConfigManager.save_config(self.config)

    def add_keyword_dialog(self):
        dialog = AddKeywordDialog(self, self.config)
        if dialog.exec_() == QDialog.Accepted:
            keyword_data = dialog.get_keyword_data()
            if keyword_data:
                self.config["keywords"].append(keyword_data)
                ConfigManager.save_config(self.config)
                self.update_keyword_list()

    def edit_keyword_dialog(self):
        current_row = self.keyword_list.currentRow()
        if current_row < 0 or current_row >= len(self.config["keywords"]):
            QMessageBox.warning(self, "警告", "请先选择一个关键字进行编辑")
            return
        
        kw = self.config["keywords"][current_row]
        dialog = EditKeywordDialog(self, kw, self.config)
        if dialog.exec_() == QDialog.Accepted:
            keyword_data = dialog.get_keyword_data()
            if keyword_data:
                keyword_data["enabled"] = kw.get("enabled", True)
                self.config["keywords"][current_row] = keyword_data
                ConfigManager.save_config(self.config)
                self.update_keyword_list()

    def delete_keyword(self):
        current_row = self.keyword_list.currentRow()
        if current_row >= 0 and current_row < len(self.config["keywords"]):
            reply = QMessageBox.question(self, "确认删除", "确定要删除这个关键字吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.config["keywords"].pop(current_row)
                ConfigManager.save_config(self.config)
                self.update_keyword_list()

    def _enabled_keywords(self):
        enabled = []
        for row, kw in enumerate(self.config["keywords"]):
            item = self.keyword_list.item(row)
            if item.checkState() == Qt.Checked:
                enabled.append(kw)
        return enabled

    def select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "All Files (*);;"
            "Windows日志文件 (*.evtx);;"
            "流量包文件 (*.pcap *.pcapng *.cap);;"
            "文档文件 (*.doc *.docx *.pdf *.txt *.rtf);;"
            "Excel文件 (*.xls *.xlsx *.csv);;"
            "PowerPoint文件 (*.ppt *.pptx);;"
            "代码文件 (*.py *.js *.jsx *.ts *.tsx *.java *.c *.cpp *.h *.hpp *.cs *.php *.rb *.go *.rs *.swift *.kt *.scala);;"
            "Web文件 (*.html *.htm *.css *.scss *.sass *.less *.vue);;"
            "配置文件 (*.json *.xml *.yaml *.yml *.ini *.cfg *.conf *.properties);;"
            "文本文件 (*.txt *.log *.md *.markdown *.rst);;"
            "脚本文件 (*.sh *.bash *.bat *.cmd *.ps1);;"
            "SQL文件 (*.sql);;"
            "其他文件 (*.*)"
        )
        if files:
            self.selected_files = files
            self.selected_files_label.setText(f"已选择 {len(files)} 个文件")

    def select_folder_recursive(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.selected_files = []
            for root, _, files in os.walk(folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    self.selected_files.append(file_path)
            self.selected_files_label.setText(f"已选择 {len(self.selected_files)} 个文件 (递归搜索)")

    def start_batch_processing(self):
        if not hasattr(self, 'selected_files') or not self.selected_files:
            QMessageBox.warning(self, "警告", "请先选择要处理的文件")
            return
        
        # 检查是否有启用的关键字
        enabled_keywords = self._enabled_keywords()
        if not enabled_keywords:
            QMessageBox.warning(self, "警告", "请至少启用一个关键字进行匹配")
            return
        
        # 如果已有线程在运行，先停止它
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self, "确认", 
                "已有处理任务正在运行，是否停止当前任务并开始新的处理？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.stop_processing()
            else:
                return
        
        # 禁用开始按钮，防止重复点击
        self.process_btn.setEnabled(False)
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("正在初始化...")
        self.stop_btn.setVisible(True)
        self.stop_btn.setEnabled(True)
        self.export_csv_btn.setVisible(False)
        self.result_text.clear()
        
        enabled_config = {
            "keywords": enabled_keywords,
            "nearby_lines": self.config["nearby_lines"],
            "nearby_chars": self.config["nearby_chars"],
            "down_lines": self.config["down_lines"],
            "up_lines": self.config["up_lines"]
        }
        
        try:
            max_workers = self.config.get("max_workers", DEFAULT_WORKER_PROCESSES)
            # WorkerThread内部会自动限制Windows上的最大进程数，这里直接传递即可
            self.worker_thread = WorkerThread(
                enabled_config,
                self.selected_files,
                self.config.get("auto_detect_encoding", True),
                max_workers=max_workers
            )
            self.worker_thread.progress_signal.connect(self.update_progress)
            self.worker_thread.line_progress_signal.connect(self.update_line_progress)
            self.worker_thread.result_signal.connect(self.show_batch_results)
            self.worker_thread.error_signal.connect(self.show_error)
            self.worker_thread.finished_signal.connect(self.processing_finished)
            self.worker_thread.start()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动处理线程失败: {str(e)}")
            self.processing_finished()

    def stop_processing(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait()
            # 停止后恢复UI状态
            self.processing_finished()

    def update_progress(self, current, total, filename):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_label.setText(f"正在处理: {filename} ({current}/{total})")
    
    def update_line_progress(self, line_no, filename):
        """更新行处理进度（用于大文件）"""
        # 直接更新标签，PyQt5的信号机制会自动处理UI更新
        self.progress_label.setText(f"正在处理: {filename} - 已处理 {line_no:,} 行")

    def _filter_excluded_blocks(self, result_text):
        """过滤掉所有已排除的关键字块"""
        lines = result_text.splitlines()
        filtered_lines = []
        skip_until_separator = False
        
        for line in lines:
            stripped = line.strip()
            
            # 检查是否是排除块的开头
            if "[已排除:" in line:
                skip_until_separator = True
                continue
            
            # 如果正在跳过排除块，检查是否到达分隔线
            if skip_until_separator:
                if stripped == "-" * 50:
                    skip_until_separator = False
                continue
            
            # 正常添加行
            filtered_lines.append(line)
        
        # 清理多余的分隔线
        cleaned, prev_separator = [], False
        for line in filtered_lines:
            stripped = line.strip()
            if stripped == "-" * 50:
                if not prev_separator:
                    cleaned.append(line)
                    prev_separator = True
                continue
            cleaned.append(line)
            prev_separator = False
        
        return "\n".join(cleaned)
    
    def show_batch_results(self, result_text, results):
        if not self.show_excluded_cb_batch.isChecked():
            result_text = self._filter_excluded_blocks(result_text)
        
        self.current_results = results
        self.result_text.setPlainText(result_text)
        self.export_csv_btn.setVisible(len(results) > 0)
        
        # 已移除自动导出功能
        # if self.config.get("auto_export", True) and results:
        #     self.auto_export_results(results, "batch")

    def show_error(self, error_msg):
        QMessageBox.critical(self, "错误", error_msg)

    def processing_finished(self):
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.stop_btn.setVisible(False)
        # 重新启用开始按钮
        self.process_btn.setEnabled(True)

    def flush_buffer(self):
        if not self.result_buffer:
            self.buffer_timer.stop()
            # 已移除自动导出功能
            # if self.config.get("auto_export", True) and self.current_results:
            #     self.auto_export_results(self.current_results, "realtime")
            return
        
        chunk = self.result_buffer[:100]
        self.result_buffer = self.result_buffer[100:]
        cursor = self.result_text_realtime.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText("\n".join(chunk) + "\n")
        
        if not self.result_buffer:
            self.buffer_timer.stop()
            # 已移除自动导出功能
            # if self.config.get("auto_export", True) and self.current_results:
            #     self.auto_export_results(self.current_results, "realtime")

    def process_realtime(self):
        text = self.input_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "警告", "请输入要匹配的文本")
            return
        
        self.result_buffer = []
        self.buffer_timer.start(100)
        
        enabled_config = {
            "keywords": self._enabled_keywords(),
            "nearby_lines": self.config["nearby_lines"],
            "nearby_chars": self.config["nearby_chars"],
            "down_lines": self.config["down_lines"],
            "up_lines": self.config["up_lines"]
        }
        
        processor = TextProcessor(enabled_config, self.config.get("auto_detect_encoding", True))
        result_text, results = processor.process_text(text, "实时输入")
        
        if not self.show_excluded_cb_realtime.isChecked():
            result_text = self._filter_excluded_blocks(result_text)
        
        self.current_results = results
        self.result_buffer = result_text.splitlines()
        self.result_buffer.append("")
        self.result_text_realtime.clear()
        self.buffer_timer.start(100)

    def auto_export_results(self, results, prefix):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(DATA_DIR, f"{prefix}_{timestamp}.csv")
            with open(filename, "w", newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'keywords', 'keywords_raw', 'remark', 'line_number', 'nearby_lines', 'nearby_chars',
                    'down_lines', 'up_lines', 'source', 'file_path', 'exclude_text', 'use_regex'
                ])
                writer.writeheader()
                for row in results:
                    writer.writerow(row)
        except Exception as e:
            QMessageBox.warning(self, "警告", f"自动导出失败: {str(e)}")

    def export_to_csv(self):
        if not self.current_results:
            QMessageBox.warning(self, "警告", "没有结果可导出")
            return
        
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出CSV",
            f"batch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        
        if filename:
            try:
                export_thread = ExportThread(self.current_results, filename)
                export_thread.start()
                export_thread.wait()
                QMessageBox.information(self, "成功", f"结果已导出到: {filename}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"导出失败: {str(e)}")

    def export_realtime_to_csv(self):
        self.export_to_csv()

    def show_batch_fullscreen(self):
        text = self.result_text.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "警告", "没有结果可全屏查看")
            return
        dialog = FullscreenResultWindow(self, text, "批量处理结果 - 全屏")
        dialog.exec_()

    def show_tree_results(self):
        if not self.current_results:
            QMessageBox.warning(self, "警告", "没有结果可结构化查看")
            return
        
        # 根据当前标签页判断使用哪个复选框的状态
        # 如果当前在批量处理标签页，使用批量处理的复选框；否则使用实时处理的复选框
        current_tab_index = self.tab_widget.currentIndex()
        if current_tab_index == 0:  # 批量处理标签页
            show_excluded = self.show_excluded_cb_batch.isChecked()
        else:  # 实时处理标签页
            show_excluded = self.show_excluded_cb_realtime.isChecked()
        
        # 根据"显示已排除提示"复选框状态过滤结果
        if show_excluded:
            # 显示所有结果（包括已排除的）
            filtered_results = self.current_results
        else:
            # 只显示未排除的结果
            filtered_results = [r for r in self.current_results if not r.get("excluded", False)]
        
        if not filtered_results:
            QMessageBox.warning(self, "警告", "没有结果可结构化查看（已排除的结果已被过滤）")
            return
        
        max_results = MAX_RESULTS_TREE
        if len(filtered_results) > max_results:
            # 创建自定义对话框，提供三个选项
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("结果过多")
            msg_box.setText(f"匹配结果数量较多({len(filtered_results)}个)")
            msg_box.setInformativeText("请选择显示方式：")
            
            # 添加自定义按钮
            btn_show_all = msg_box.addButton("显示全部", QMessageBox.YesRole)
            btn_show_partial = msg_box.addButton(f"仅显示前{max_results}个", QMessageBox.NoRole)
            btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            # 设置默认按钮
            msg_box.setDefaultButton(btn_show_all)
            
            msg_box.exec_()
            clicked_button = msg_box.clickedButton()
            
            # 通过比较按钮对象来判断用户的选择
            if clicked_button == btn_cancel:  # 取消
                return
            elif clicked_button == btn_show_partial:  # 仅显示前5000个
                display_results = filtered_results[:max_results]
            else:  # 显示全部（默认或点击了显示全部按钮）
                display_results = filtered_results
        else:
            display_results = filtered_results
        
        # 清理已关闭的窗口引用
        self.tree_result_windows = [w for w in self.tree_result_windows if w is not None and w.isVisible()]
        
        # 计算窗口位置，避免新窗口重叠（每个窗口偏移30像素）
        window_count = len(self.tree_result_windows)
        offset_x = window_count * 30
        offset_y = window_count * 30
        
        # 创建新的非模态窗口（允许多个窗口同时存在）
        new_window = TreeResultWindow(self, display_results, f"批量处理结果 - 结构化 ({window_count + 1})")
        
        # 设置窗口位置
        new_window.move(100 + offset_x, 100 + offset_y)
        
        # 添加到窗口列表
        self.tree_result_windows.append(new_window)
        
        # 窗口关闭时从列表中移除
        def remove_window(window_ref):
            try:
                if window_ref in self.tree_result_windows:
                    self.tree_result_windows.remove(window_ref)
            except:
                pass
        
        new_window.destroyed.connect(lambda: remove_window(new_window))
        
        # 使用show()而不是exec_()，允许非模态显示
        new_window.show()
        # 将窗口提升到最前面
        new_window.raise_()
        new_window.activateWindow()

    def show_realtime_fullscreen(self):
        text = self.result_text_realtime.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "警告", "没有结果可全屏查看")
            return
        dialog = FullscreenResultWindow(self, text, "实时处理结果 - 全屏")
        dialog.exec_()
    
    def restore_geometry(self):
        """恢复窗口大小和位置"""
        geometry = self.settings.value("main_window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # 默认大小和位置
            self.setGeometry(100, 100, 1200, 800)
    
    def export_config(self):
        """导出配置文件"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出配置文件",
            f"config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            success, error_msg = ConfigManager.export_config(filename)
            if success:
                QMessageBox.information(self, "成功", f"配置文件已导出到：\n{filename}")
            else:
                QMessageBox.critical(self, "错误", f"导出配置文件失败：\n{error_msg}")
    
    def import_config(self):
        """导入配置文件"""
        reply = QMessageBox.question(
            self, "确认导入",
            "导入配置文件将覆盖当前配置，是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        filename, _ = QFileDialog.getOpenFileName(
            self, "导入配置文件",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if filename:
            success, result = ConfigManager.import_config(filename)
            if success:
                # 重新加载配置
                self.config = result
                # 更新UI
                self.lines_spin.setValue(self.config["nearby_lines"])
                self.chars_spin.setValue(self.config["nearby_chars"])
                self.down_spin.setValue(self.config.get("down_lines", 0))
                self.up_spin.setValue(self.config.get("up_lines", 0))
                self.auto_export_cb.setChecked(self.config.get("auto_export", True))
                self.auto_detect_encoding_cb.setChecked(self.config.get("auto_detect_encoding", True))
                self.workers_spin.setValue(self.config.get("max_workers", DEFAULT_WORKER_PROCESSES))
                self.update_keyword_list()
                QMessageBox.information(self, "成功", "配置文件已成功导入！")
            else:
                QMessageBox.critical(self, "错误", f"导入配置文件失败：\n{result}")
    
    def closeEvent(self, event):
        """窗口关闭时保存大小和位置，并清理所有资源"""
        # 停止并等待工作线程完成
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            # 等待线程结束，但设置超时避免无限等待
            if not self.worker_thread.wait(3000):  # 3秒超时
                # 如果线程还在运行，强制终止
                try:
                    self.worker_thread.terminate()
                    self.worker_thread.wait(1000)  # 再等待1秒
                except:
                    pass
        
        # 强制清理所有进程池和子进程
        try:
            cleanup_all_processes()
        except:
            pass
        
        # 关闭所有结构化结果窗口
        for window in self.tree_result_windows:
            if window and window.isVisible():
                try:
                    window.close()
                except:
                    pass
        
        # 停止定时器
        if self.buffer_timer.isActive():
            self.buffer_timer.stop()
        
        # 保存窗口大小和位置
        try:
            self.settings.setValue("main_window/geometry", self.saveGeometry())
        except:
            pass
        
        event.accept()