# -*- coding: utf-8 -*-
import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, 
    QHBoxLayout, QMessageBox, QMenu, QAction, QApplication, QStyledItemDelegate, QStyle,
    QAbstractItemView, QLabel, QButtonGroup, QRadioButton
)
from PyQt5.QtCore import Qt, QSize, QSettings
from PyQt5.QtGui import QTextCharFormat, QColor, QSyntaxHighlighter, QFont, QFontMetrics
from constants import FILES_PER_PAGE, MATCHES_PER_FILE_PER_PAGE, MAX_CONTENT_LENGTH


class WrapTextDelegate(QStyledItemDelegate):
    """支持文本换行的委托类"""
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def sizeHint(self, option, index):
        """计算行高以适应多行文本，使表格更紧凑"""
        font = option.font
        font_metrics = QFontMetrics(font)
        base_height = font_metrics.height() + 4  # 基础行高：字体高度 + 4像素边距
        compact_height = font_metrics.height() + 2  # 紧凑行高：字体高度 + 2像素边距
        
        if index.column() == 3:  # 内容列
            text = index.data(Qt.DisplayRole) or ""
            if text and text.strip():
                # 计算文本需要的宽度（列宽 - 边距）
                text_width = option.rect.width() - 8 if option.rect.width() > 0 else 392
                # 如果列宽为0，使用默认宽度
                if text_width <= 0:
                    text_width = 392
                # 使用boundingRect计算文本换行后的高度
                text_rect = font_metrics.boundingRect(
                    0, 0, text_width, 0,
                    Qt.TextWordWrap | Qt.AlignTop | Qt.AlignLeft,
                    text
                )
                # 减少边距，使表格更紧凑：只保留最小的上下边距（各2像素，共4像素）
                # boundingRect的高度已经包含了行高，我们只需要添加少量边距
                height = text_rect.height() + 4
                # 最小高度设为字体高度 + 少量边距
                height = max(height, base_height)
                return QSize(text_width, height)
            else:
                # 内容列为空时，使用紧凑高度
                return QSize(option.rect.width() if option.rect.width() > 0 else 392, compact_height)
        
        # 对于其他列（文件、关键字、行号），使用紧凑的基础行高
        text = index.data(Qt.DisplayRole) or ""
        if not text.strip():
            # 空文本使用紧凑行高
            return QSize(option.rect.width() if option.rect.width() > 0 else 100, compact_height)
        
        # 有文本的列，使用基础行高
        return QSize(option.rect.width() if option.rect.width() > 0 else 100, base_height)
    
    def paint(self, painter, option, index):
        """绘制多行文本"""
        if index.column() == 3:  # 内容列
            # 绘制背景
            if option.state & QStyle.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            elif option.state & QStyle.State_MouseOver:
                painter.fillRect(option.rect, option.palette.light())
            else:
                painter.fillRect(option.rect, option.palette.base())
            
            text = index.data(Qt.DisplayRole) or ""
            if text:
                painter.save()
                
                # 根据选中状态设置文本颜色
                if option.state & (QStyle.State_Selected | QStyle.State_HasFocus):
                    painter.setPen(option.palette.highlightedText().color())
                else:
                    painter.setPen(option.palette.text().color())
                
                # 设置字体
                painter.setFont(option.font)
                
                # 绘制文本（支持换行），减少边距使表格更紧凑
                text_rect = option.rect.adjusted(4, 2, -4, -2)
                painter.drawText(
                    text_rect,
                    Qt.TextWordWrap | Qt.AlignTop | Qt.AlignLeft,
                    text
                )
                painter.restore()
                return
        super().paint(painter, option, index)

class TreeResultWindow(QDialog):
    def __init__(self, parent=None, results=None, title="结构化结果"):
        super().__init__(parent)
        self.settings = QSettings("CongSec", "TextProcessor")
        self.setWindowTitle(title)
        self.results = results or []
        self.current_item = None
        self.tree_items = []
        # 视图模式：'file' 按文件分类，'keyword' 按关键字分类
        self.view_mode = 'file'
        # 分页相关变量
        self.file_groups = {}  # 存储按文件分组的结果
        self.file_list = []  # 存储文件路径列表
        self.current_file_page = 1  # 当前文件页码
        self.file_pages = {}  # 存储每个文件的匹配项分页信息 {file_path: {page: matches}}
        # 关键字分组相关变量
        self.keyword_groups = {}  # 存储按关键字分组的结果
        self.keyword_list = []  # 存储关键字列表
        self.current_keyword_page = 1  # 当前关键字页码
        # 设置为非模态窗口，允许同时使用其他功能
        self.setModal(False)
        # 设置窗口标志，使其可以独立存在并支持最小化
        self.setWindowFlags(self.windowFlags() | Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)
        self.init_ui()
        # 恢复窗口大小
        self.restore_geometry()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["文件", "关键字", "行号", "内容"])
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.tree_widget.currentItemChanged.connect(self.on_item_changed)
        self.tree_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        # 设置内容列支持换行显示
        header = self.tree_widget.header()
        header.setStretchLastSection(True)
        self.tree_widget.setColumnWidth(3, 400)
        # 为所有列设置委托，使行高更紧凑，减少空行
        wrap_delegate = WrapTextDelegate(self.tree_widget)
        # 为所有列设置委托，确保所有列都使用紧凑的行高
        for col in range(4):  # 4列：文件、关键字、行号、内容
            self.tree_widget.setItemDelegateForColumn(col, wrap_delegate)
        # 设置默认行高，支持多行文本显示，使用紧凑模式
        self.tree_widget.setRootIsDecorated(True)
        # 设置统一的项高模式，让行高更紧凑
        self.tree_widget.setUniformRowHeights(False)  # False允许每行有不同的高度
        # 设置滚动模式为像素级滚动，使滚动更平滑（不再是按行滚动）
        self.tree_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree_widget.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        
        # 视图切换控件
        view_layout = QHBoxLayout()
        view_layout.addWidget(QLabel("视图模式:"))
        self.view_mode_group = QButtonGroup(self)
        self.file_view_radio = QRadioButton("按文件分类")
        self.file_view_radio.setChecked(True)
        self.keyword_view_radio = QRadioButton("按关键字分类")
        self.view_mode_group.addButton(self.file_view_radio, 0)
        self.view_mode_group.addButton(self.keyword_view_radio, 1)
        self.file_view_radio.toggled.connect(self.on_view_mode_changed)
        self.keyword_view_radio.toggled.connect(self.on_view_mode_changed)
        view_layout.addWidget(self.file_view_radio)
        view_layout.addWidget(self.keyword_view_radio)
        view_layout.addStretch()
        layout.addLayout(view_layout)
        
        # 初始化数据分组
        self._prepare_data()
        
        # 分页控件
        pagination_layout = QHBoxLayout()
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self.go_to_prev_page)
        self.page_label = QLabel()
        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self.go_to_next_page)
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.page_label)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.next_btn)
        
        layout.addLayout(pagination_layout)
        layout.addWidget(self.tree_widget)
        
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)  # 使用close()而不是accept()，支持非模态窗口
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)
        
        # 根据默认视图模式设置列的可见性（默认是文件视图，关键字列显示）
        self.tree_widget.setColumnHidden(1, False)
        
        # 显示第一页
        self.populate_tree_batched()
    
    def restore_geometry(self):
        """恢复窗口大小"""
        geometry = self.settings.value("tree_result_window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # 默认大小
            self.setGeometry(100, 100, 1000, 700)
    
    def closeEvent(self, event):
        """窗口关闭时保存大小"""
        self.settings.setValue("tree_result_window/geometry", self.saveGeometry())
        super().closeEvent(event)

    def _prepare_data(self):
        """准备数据：按文件分组和按关键字分组，并计算分页信息"""
        # 按文件分组
        self.file_groups = {}
        for result in self.results:
            file_path = result.get("file_path", "未知文件")
            if file_path not in self.file_groups:
                self.file_groups[file_path] = []
            self.file_groups[file_path].append(result)
        
        self.file_list = list(self.file_groups.keys())
        
        # 计算每个文件的匹配项分页信息
        self.file_pages = {}
        for file_path, file_results in self.file_groups.items():
            total_matches = len(file_results)
            total_pages = (total_matches + MATCHES_PER_FILE_PER_PAGE - 1) // MATCHES_PER_FILE_PER_PAGE
            self.file_pages[file_path] = {
                'total_matches': total_matches,
                'total_pages': total_pages if total_pages > 0 else 1
            }
        
        # 计算文件分页信息
        self.total_file_pages = (len(self.file_list) + FILES_PER_PAGE - 1) // FILES_PER_PAGE if self.file_list else 1
        
        # 按关键字分组
        self.keyword_groups = {}
        for result in self.results:
            keyword = result.get("keywords", "未知关键字")
            if keyword not in self.keyword_groups:
                self.keyword_groups[keyword] = []
            self.keyword_groups[keyword].append(result)
        
        self.keyword_list = list(self.keyword_groups.keys())
        
        # 计算关键字分页信息
        self.total_keyword_pages = (len(self.keyword_list) + FILES_PER_PAGE - 1) // FILES_PER_PAGE if self.keyword_list else 1
    
    def get_current_page_files(self):
        """获取当前页应该显示的文件列表"""
        start_idx = (self.current_file_page - 1) * FILES_PER_PAGE
        end_idx = start_idx + FILES_PER_PAGE
        return self.file_list[start_idx:end_idx]
    
    def get_current_page_keywords(self):
        """获取当前页应该显示的关键字列表"""
        start_idx = (self.current_keyword_page - 1) * FILES_PER_PAGE
        end_idx = start_idx + FILES_PER_PAGE
        return self.keyword_list[start_idx:end_idx]
    
    def get_file_matches_for_page(self, file_path, page=1):
        """获取指定文件指定页的匹配项"""
        file_results = self.file_groups.get(file_path, [])
        start_idx = (page - 1) * MATCHES_PER_FILE_PER_PAGE
        end_idx = start_idx + MATCHES_PER_FILE_PER_PAGE
        return file_results[start_idx:end_idx]
    
    def populate_tree_batched(self):
        """填充树形视图（支持分页，支持按文件和按关键字两种视图）"""
        self.tree_widget.clear()
        self.tree_items.clear()
        
        if self.view_mode == 'file':
            self._populate_tree_by_file()
        else:
            self._populate_tree_by_keyword()
        
        # 更新分页控件状态
        self._update_pagination_ui()
    
    def _populate_tree_by_file(self):
        """按文件填充树形视图"""
        # 获取当前页的文件列表
        current_files = self.get_current_page_files()
        
        for file_path in current_files:
            file_results = self.file_groups[file_path]
            # 直接显示该文件的所有匹配项，不再分页
            total_matches = len(file_results)
            
            # 构建文件项标题（包含匹配项总数）
            file_title = f"{os.path.basename(file_path)} (共 {total_matches} 个匹配)"
            
            file_item = QTreeWidgetItem([file_title, "", "", ""])
            # 存储完整的文件结果（用于复制等功能）
            file_item.setData(0, Qt.UserRole, {"type": "file", "data": file_results, "file_path": file_path})
            file_item.setExpanded(False)
            
            # 添加所有匹配项
            for result in file_results:
                # 构建内容列显示：只显示附近字符（去掉换行符），不显示上下行内容
                nearby_chars = result.get("nearby_chars", "")
                if nearby_chars:
                    # 去掉换行符，替换为空格
                    nearby_chars_cleaned = nearby_chars.replace("\n", " ").replace("\r", " ")
                    # 去除多余空格
                    nearby_chars_cleaned = " ".join(nearby_chars_cleaned.split())
                    content_text = nearby_chars_cleaned
                else:
                    # 如果没有任何内容，显示默认信息
                    content_text = f"第 {result.get('line_number', '')} 行"
                
                # 检查是否被排除，添加标记
                is_excluded = result.get("excluded", False)
                keywords_text = result.get("keywords", "")
                if is_excluded:
                    exclude_text = result.get("exclude_text", "")
                    keywords_text = f"{keywords_text} [已排除: {exclude_text}]"
                
                main_item = QTreeWidgetItem([
                    "",  # 文件视图下，文件名已在父项显示，这里留空
                    keywords_text,
                    str(result.get("line_number", "")),
                    content_text
                ])
                # 设置内容列（索引3）的文本对齐方式，允许换行
                main_item.setTextAlignment(3, Qt.AlignTop | Qt.AlignLeft)
                # 如果被排除，设置背景色为浅红色
                if is_excluded:
                    for col in range(4):
                        main_item.setBackground(col, QColor(255, 240, 240))
                main_item.setData(0, Qt.UserRole, {"type": "match", "data": result})
                if result.get("nearby_lines") or result.get("nearby_chars") or result.get("down_lines") or result.get("up_lines"):
                    placeholder = QTreeWidgetItem(["", "", "", "双击展开详细内容..."])
                    placeholder.setData(0, Qt.UserRole, {"type": "placeholder", "data": result})
                    main_item.addChild(placeholder)
                file_item.addChild(main_item)
                self.tree_items.append(main_item)
            
            self.tree_widget.addTopLevelItem(file_item)
            self.tree_items.append(file_item)
    
    def _populate_tree_by_keyword(self):
        """按关键字填充树形视图"""
        # 获取当前页的关键字列表
        current_keywords = self.get_current_page_keywords()
        
        for keyword in current_keywords:
            keyword_results = self.keyword_groups[keyword]
            # 直接显示该关键字的所有匹配项
            total_matches = len(keyword_results)
            
            # 构建关键字项标题（包含匹配项总数）
            keyword_title = f"{keyword} (共 {total_matches} 个匹配)"
            
            keyword_item = QTreeWidgetItem([keyword_title, "", "", ""])
            # 存储完整的关键字结果（用于复制等功能）
            keyword_item.setData(0, Qt.UserRole, {"type": "keyword", "data": keyword_results, "keyword": keyword})
            keyword_item.setExpanded(False)
            
            # 添加所有匹配项
            for result in keyword_results:
                # 构建内容列显示：只显示附近字符（去掉换行符），不显示上下行内容
                nearby_chars = result.get("nearby_chars", "")
                if nearby_chars:
                    # 去掉换行符，替换为空格
                    nearby_chars_cleaned = nearby_chars.replace("\n", " ").replace("\r", " ")
                    # 去除多余空格
                    nearby_chars_cleaned = " ".join(nearby_chars_cleaned.split())
                    content_text = nearby_chars_cleaned
                else:
                    # 如果没有任何内容，显示默认信息
                    content_text = f"第 {result.get('line_number', '')} 行"
                
                # 检查是否被排除，在内容列添加标记
                is_excluded = result.get("excluded", False)
                file_name = os.path.basename(result.get("file_path", ""))
                if is_excluded:
                    exclude_text = result.get("exclude_text", "")
                    content_text = f"[已排除: {exclude_text}] {content_text}"
                
                main_item = QTreeWidgetItem([
                    file_name,
                    "",  # 按关键字分类时，关键字已在父项显示，这里留空
                    str(result.get("line_number", "")),
                    content_text
                ])
                # 设置内容列（索引3）的文本对齐方式，允许换行
                main_item.setTextAlignment(3, Qt.AlignTop | Qt.AlignLeft)
                # 如果被排除，设置背景色为浅红色
                if is_excluded:
                    for col in range(4):
                        main_item.setBackground(col, QColor(255, 240, 240))
                main_item.setData(0, Qt.UserRole, {"type": "match", "data": result})
                if result.get("nearby_lines") or result.get("nearby_chars") or result.get("down_lines") or result.get("up_lines"):
                    placeholder = QTreeWidgetItem(["", "", "", "双击展开详细内容..."])
                    placeholder.setData(0, Qt.UserRole, {"type": "placeholder", "data": result})
                    main_item.addChild(placeholder)
                keyword_item.addChild(main_item)
                self.tree_items.append(main_item)
            
            self.tree_widget.addTopLevelItem(keyword_item)
            self.tree_items.append(keyword_item)
    
    def _update_pagination_ui(self):
        """更新分页控件UI"""
        if self.view_mode == 'file':
            total_items = len(self.file_list)
            if total_items == 0:
                self.page_label.setText("无结果")
                self.prev_btn.setEnabled(False)
                self.next_btn.setEnabled(False)
            else:
                self.page_label.setText(f"文件页: {self.current_file_page}/{self.total_file_pages} (共 {total_items} 个文件)")
                self.prev_btn.setEnabled(self.current_file_page > 1)
                self.next_btn.setEnabled(self.current_file_page < self.total_file_pages)
        else:
            total_items = len(self.keyword_list)
            if total_items == 0:
                self.page_label.setText("无结果")
                self.prev_btn.setEnabled(False)
                self.next_btn.setEnabled(False)
            else:
                self.page_label.setText(f"关键字页: {self.current_keyword_page}/{self.total_keyword_pages} (共 {total_items} 个关键字)")
                self.prev_btn.setEnabled(self.current_keyword_page > 1)
                self.next_btn.setEnabled(self.current_keyword_page < self.total_keyword_pages)
    
    def go_to_prev_page(self):
        """跳转到上一页"""
        if self.view_mode == 'file':
            if self.current_file_page > 1:
                self.current_file_page -= 1
                self.populate_tree_batched()
        else:
            if self.current_keyword_page > 1:
                self.current_keyword_page -= 1
                self.populate_tree_batched()
    
    def go_to_next_page(self):
        """跳转到下一页"""
        if self.view_mode == 'file':
            if self.current_file_page < self.total_file_pages:
                self.current_file_page += 1
                self.populate_tree_batched()
        else:
            if self.current_keyword_page < self.total_keyword_pages:
                self.current_keyword_page += 1
                self.populate_tree_batched()
    
    def on_view_mode_changed(self):
        """视图模式改变时的处理"""
        if self.file_view_radio.isChecked():
            self.view_mode = 'file'
            self.current_file_page = 1
            # 显示关键字列
            self.tree_widget.setColumnHidden(1, False)
        else:
            self.view_mode = 'keyword'
            self.current_keyword_page = 1
            # 隐藏关键字列（因为已按关键字分组）
            self.tree_widget.setColumnHidden(1, True)
        self.populate_tree_batched()

    def truncate_text(self, text, max_length=100):
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    def on_item_double_clicked(self, item, column):
        try:
            data = item.data(0, Qt.UserRole)
            if not data:
                return
            item_type = data.get("type")
            if item_type == "match":
                if item.childCount() == 0 or (item.childCount() == 1 and item.child(0).data(0, Qt.UserRole).get("type") == "placeholder"):
                    item.takeChildren()
                    result_data = data.get("data", {})
                    detail_items = self.load_detail_content(result_data)
                    for detail_item in detail_items:
                        item.addChild(detail_item)
            elif item_type == "placeholder":
                parent = item.parent()
                if parent:
                    parent_data = parent.data(0, Qt.UserRole)
                    if parent_data and parent_data.get("type") == "match":
                        parent.takeChildren()
                        result_data = parent_data.get("data", {})
                        detail_items = self.load_detail_content(result_data)
                        for detail_item in detail_items:
                            parent.addChild(detail_item)
        except Exception as e:
            pass

    def load_detail_content(self, result_data):
        detail_items = []
        try:
            # 显示附近行内容（不显示列名前缀，直接显示内容）
            if result_data.get("nearby_lines"):
                nearby_text = result_data.get("nearby_lines", "")
                if len(nearby_text) > MAX_CONTENT_LENGTH:
                    nearby_text = nearby_text[:MAX_CONTENT_LENGTH] + "..."
                nearby_item = QTreeWidgetItem(["", "附近行内容", "", nearby_text])
                nearby_item.setTextAlignment(3, Qt.AlignTop | Qt.AlignLeft)
                nearby_item.setData(0, Qt.UserRole, {"type": "content", "content": result_data.get("nearby_lines"), "label": "附近行内容"})
                detail_items.append(nearby_item)
            
            # 显示附近字符内容（不显示列名前缀，直接显示内容，去掉换行符）
            if result_data.get("nearby_chars"):
                chars_text = result_data.get("nearby_chars", "")
                # 去掉换行符，替换为空格
                chars_text_cleaned = chars_text.replace("\n", " ").replace("\r", " ")
                # 去除多余空格
                chars_text_cleaned = " ".join(chars_text_cleaned.split())
                if len(chars_text_cleaned) > MAX_CONTENT_LENGTH:
                    chars_text_cleaned = chars_text_cleaned[:MAX_CONTENT_LENGTH] + "..."
                chars_item = QTreeWidgetItem(["", "附近字符", "", chars_text_cleaned])
                chars_item.setTextAlignment(3, Qt.AlignTop | Qt.AlignLeft)
                chars_item.setData(0, Qt.UserRole, {"type": "content", "content": result_data.get("nearby_chars"), "label": "附近字符"})
                detail_items.append(chars_item)
            
            # 显示上行内容（不显示列名前缀，直接显示内容）
            if result_data.get("up_lines"):
                up_text = result_data.get("up_lines", "")
                if len(up_text) > MAX_CONTENT_LENGTH:
                    up_text = up_text[:MAX_CONTENT_LENGTH] + "..."
                up_item = QTreeWidgetItem(["", "上行内容", "", up_text])
                up_item.setTextAlignment(3, Qt.AlignTop | Qt.AlignLeft)
                up_item.setData(0, Qt.UserRole, {"type": "content", "content": result_data.get("up_lines"), "label": "上行内容"})
                detail_items.append(up_item)
            
            # 显示下行内容（不显示列名前缀，直接显示内容）
            if result_data.get("down_lines"):
                down_text = result_data.get("down_lines", "")
                if len(down_text) > MAX_CONTENT_LENGTH:
                    down_text = down_text[:MAX_CONTENT_LENGTH] + "..."
                down_item = QTreeWidgetItem(["", "下行内容", "", down_text])
                down_item.setTextAlignment(3, Qt.AlignTop | Qt.AlignLeft)
                down_item.setData(0, Qt.UserRole, {"type": "content", "content": result_data.get("down_lines"), "label": "下行内容"})
                detail_items.append(down_item)
            
            # 如果被排除，显示排除信息
            if result_data.get("excluded"):
                exclude_text = result_data.get("exclude_text", "")
                exclude_region = result_data.get("exclude_match_region", "")
                exclude_content = result_data.get("exclude_match_content", "")
                
                if exclude_text:
                    exclude_info = f"排除文本: {exclude_text}"
                    if exclude_region:
                        exclude_info += f"\n排除文本匹配区域: {exclude_region}"
                    if exclude_content:
                        exclude_content_display = exclude_content
                        if len(exclude_content_display) > MAX_CONTENT_LENGTH:
                            exclude_content_display = exclude_content_display[:MAX_CONTENT_LENGTH] + "..."
                        exclude_info += f"\n排除文本匹配内容:\n{exclude_content_display}"
                    
                    exclude_item = QTreeWidgetItem(["", "排除信息", "", exclude_info])
                    exclude_item.setTextAlignment(3, Qt.AlignTop | Qt.AlignLeft)
                    exclude_item.setData(0, Qt.UserRole, {"type": "content", "content": exclude_info, "label": "排除信息"})
                    # 设置背景色为浅红色
                    for col in range(4):
                        exclude_item.setBackground(col, QColor(255, 240, 240))
                    detail_items.append(exclude_item)
        except Exception:
            error_item = QTreeWidgetItem(["", "", "", "加载详细内容时出错"])
            error_item.setData(0, Qt.UserRole, {"type": "error", "content": "加载详细内容时出错"})
            detail_items.append(error_item)
        return detail_items

    def on_item_changed(self, current, previous):
        if current:
            self.current_item = current

    def show_context_menu(self, position):
        try:
            item = self.tree_widget.itemAt(position)
            if not item:
                return
            self.current_item = item
            data = item.data(0, Qt.UserRole)
            if not data:
                return
            menu = QMenu(self)
            item_type = data.get("type")
            if item_type == "content":
                copy_content_action = QAction("复制内容", self)
                copy_content_action.triggered.connect(lambda: self.copy_content(data.get("content", "")))
                menu.addAction(copy_content_action)
                copy_with_label_action = QAction("复制带标签的内容", self)
                copy_with_label_action.triggered.connect(lambda: self.copy_with_label(data.get("label", ""), data.get("content", "")))
                menu.addAction(copy_with_label_action)
            elif item_type == "match":
                result_data = data.get("data", {})
                copy_keywords_action = QAction("复制关键字", self)
                copy_keywords_action.triggered.connect(lambda: self.copy_to_clipboard(result_data.get("keywords", "")))
                menu.addAction(copy_keywords_action)
                copy_line_number_action = QAction("复制行号", self)
                copy_line_number_action.triggered.connect(lambda: self.copy_to_clipboard(str(result_data.get("line_number", ""))))
                menu.addAction(copy_line_number_action)
                copy_location_action = QAction("复制位置", self)
                copy_location_action.triggered.connect(lambda: self.copy_location(result_data))
                menu.addAction(copy_location_action)
                copy_all_info_action = QAction("复制完整信息", self)
                copy_all_info_action.triggered.connect(lambda: self.copy_all_info(result_data))
                menu.addAction(copy_all_info_action)
                open_in_editor_action = QAction("在 Notepad++ 中打开位置", self)
                open_in_editor_action.triggered.connect(lambda: self.open_in_notepad_plus_plus(result_data))
                menu.addAction(open_in_editor_action)
            elif item_type == "file":
                copy_filename_action = QAction("复制文件名", self)
                copy_filename_action.triggered.connect(lambda: self.copy_filename(item))
                menu.addAction(copy_filename_action)
                copy_all_matches_action = QAction("复制该文件所有匹配", self)
                copy_all_matches_action.triggered.connect(lambda: self.copy_file_matches(data.get("data", [])))
                menu.addAction(copy_all_matches_action)
            elif item_type == "keyword":
                copy_keyword_action = QAction("复制关键字", self)
                copy_keyword_action.triggered.connect(lambda: self.copy_to_clipboard(data.get("keyword", "")))
                menu.addAction(copy_keyword_action)
                copy_all_matches_action = QAction("复制该关键字所有匹配", self)
                copy_all_matches_action.triggered.connect(lambda: self.copy_keyword_matches(data.get("data", [])))
                menu.addAction(copy_all_matches_action)
            copy_item_text_action = QAction("复制当前行文本", self)
            copy_item_text_action.triggered.connect(lambda: self.copy_item_text(item))
            menu.addAction(copy_item_text_action)
            menu.exec_(self.tree_widget.viewport().mapToGlobal(position))
        except Exception:
            pass

    def open_in_notepad_plus_plus(self, result_data):
        try:
            file_path = result_data.get("file_path", "")
            line_number = result_data.get("line_number", 1)
            if not os.path.exists(file_path):
                QMessageBox.warning(self, "打开失败", f"文件不存在：\n{file_path}")
                return
            notepad_paths = [
                r"D:\Notepad++\notepad++.exe",
                r"C:\Program Files (x86)\Notepad++\notepad++.exe",
                r"C:\Apps\Notepad++\notepad++.exe"
            ]
            notepad_exe = None
            for path in notepad_paths:
                if os.path.exists(path):
                    notepad_exe = path
                    break
            if not notepad_exe:
                try:
                    import winreg
                    reg_paths = [
                        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Notepad++"),
                        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Notepad++")
                    ]
                    for hkey, reg_path in reg_paths:
                        try:
                            with winreg.OpenKey(hkey, reg_path) as key:
                                install_dir = winreg.QueryValueEx(key, "InstallLocation")[0]
                                exe_path = os.path.join(install_dir, "notepad++.exe")
                                if os.path.exists(exe_path):
                                    notepad_exe = exe_path
                                    break
                        except (FileNotFoundError, OSError):
                            continue
                except ImportError:
                    pass
            if not notepad_exe:
                QMessageBox.warning(self, "Notepad++ 未找到",
                                  "无法自动找到 Notepad++ 安装路径，请确保 Notepad++ 已安装。\n"
                                  "支持的安装路径包括：\n"
                                  "C:\\Program Files\\Notepad++\\\n"
                                  "C:\\Program Files (x86)\\Notepad++\\\n"
                                  "或者通过注册表自动查找")
                return
            import subprocess
            subprocess.Popen([notepad_exe, f"-n{line_number}", file_path])
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开 Notepad++：\n{str(e)}")

    def copy_to_clipboard(self, text):
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
        except Exception:
            pass

    def copy_content(self, content):
        self.copy_to_clipboard(content)

    def copy_with_label(self, label, content):
        text = f"{label}:\n{content}"
        self.copy_to_clipboard(text)

    def copy_filename(self, item):
        try:
            filename = item.text(0)
            self.copy_to_clipboard(filename)
        except Exception:
            pass

    def copy_location(self, result_data):
        try:
            location = f"文件: {result_data.get('source', '')}\n关键字: {result_data.get('keywords', '')}\n行号: {result_data.get('line_number', '')}"
            self.copy_to_clipboard(location)
        except Exception:
            pass

    def copy_all_info(self, result_data):
        try:
            info_lines = []
            info_lines.append(f"文件: {result_data.get('source', '')}")
            info_lines.append(f"关键字: {result_data.get('keywords', '')}")
            info_lines.append(f"行号: {result_data.get('line_number', '')}")
            if result_data.get("nearby_lines"):
                info_lines.append(f"附近行内容:\n{result_data.get('nearby_lines')}")
            if result_data.get("nearby_chars"):
                info_lines.append(f"附近字符:\n{result_data.get('nearby_chars')}")
            if result_data.get("down_lines"):
                info_lines.append(f"向下行内容:\n{result_data.get('down_lines')}")
            if result_data.get("up_lines"):
                info_lines.append(f"向上行内容:\n{result_data.get('up_lines')}")
            if result_data.get("exclude_text"):
                info_lines.append(f"排除文本: {result_data.get('exclude_text')}")
            info_text = "\n".join(info_lines)
            self.copy_to_clipboard(info_text)
        except Exception:
            pass

    def copy_file_matches(self, file_results):
        try:
            all_matches = []
            for result in file_results:
                match_info = f"关键字: {result.get('keywords', '')} (行 {result.get('line_number', '')})"
                if result.get("nearby_lines"):
                    match_info += f"\n附近行: {result.get('nearby_lines')}"
                if result.get("nearby_chars"):
                    match_info += f"\n附近字符: {result.get('nearby_chars')}"
                if result.get("down_lines"):
                    match_info += f"\n向下行: {result.get('down_lines')}"
                if result.get("up_lines"):
                    match_info += f"\n向上行: {result.get('up_lines')}"
                all_matches.append(match_info)
            text = f"文件 {file_results[0].get('source', '') if file_results else ''} 的所有匹配:\n" + "\n---\n".join(all_matches)
            self.copy_to_clipboard(text)
        except Exception:
            pass
    
    def copy_keyword_matches(self, keyword_results):
        try:
            all_matches = []
            for result in keyword_results:
                match_info = f"文件: {result.get('source', '')} (行 {result.get('line_number', '')})"
                if result.get("nearby_lines"):
                    match_info += f"\n附近行: {result.get('nearby_lines')}"
                if result.get("nearby_chars"):
                    match_info += f"\n附近字符: {result.get('nearby_chars')}"
                if result.get("down_lines"):
                    match_info += f"\n向下行: {result.get('down_lines')}"
                if result.get("up_lines"):
                    match_info += f"\n向上行: {result.get('up_lines')}"
                all_matches.append(match_info)
            keyword = keyword_results[0].get('keywords', '') if keyword_results else ''
            text = f"关键字 {keyword} 的所有匹配:\n" + "\n---\n".join(all_matches)
            self.copy_to_clipboard(text)
        except Exception:
            pass

    def copy_item_text(self, item):
        try:
            texts = []
            for i in range(item.columnCount()):
                text = item.text(i)
                if text:
                    texts.append(text)
            full_text = " | ".join(texts)
            self.copy_to_clipboard(full_text)
        except Exception:
            pass