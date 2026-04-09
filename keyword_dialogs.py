# -*- coding: utf-8 -*-
import re
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QPlainTextEdit, QSpinBox, QCheckBox, 
    QLabel, QDialogButtonBox, QHBoxLayout, QPushButton, QMessageBox,
    QTextBrowser
)
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtGui import QFont

class KeywordDialog(QDialog):
    """关键字对话框基类"""
    
    def __init__(self, parent=None, title="添加关键字", config=None):
        super().__init__(parent)
        self.config = config or {}
        self.settings = QSettings("CongSec", "TextProcessor")
        self.setWindowTitle(title)
        self.setModal(True)
        self.init_ui()
        # 恢复窗口大小
        self.restore_geometry()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 备注输入区域
        remark_layout = QVBoxLayout()
        remark_layout.addWidget(QLabel("备注（可选，用于描述此关键字的作用，将优先显示在列表中）:"))
        self.remark_edit = QPlainTextEdit()
        self.remark_edit.setMaximumHeight(60)
        self.remark_edit.setPlaceholderText("请输入备注信息，例如：查找密码、搜索用户名等")
        remark_layout.addWidget(self.remark_edit)
        layout.addLayout(remark_layout)
        
        # 关键字输入区域
        keyword_layout = QVBoxLayout()
        keyword_layout.addWidget(QLabel("关键字（每行一个关键字）:"))
        self.keyword_edit = QPlainTextEdit()
        self.keyword_edit.setMaximumHeight(80)
        self.keyword_edit.setPlaceholderText("每行一个关键字\n使用正则表达式时请勾选下方选项")
        keyword_layout.addWidget(self.keyword_edit)
        
        # 正则表达式测试区域
        regex_test_layout = QHBoxLayout()
        self.regex_test_btn = QPushButton("测试正则表达式")
        self.regex_test_btn.clicked.connect(self.test_regex)
        regex_test_layout.addWidget(self.regex_test_btn)
        # 添加问号帮助按钮
        self.regex_help_btn = QPushButton("?")
        self.regex_help_btn.setMaximumWidth(30)
        self.regex_help_btn.setToolTip("点击查看正则表达式语法说明")
        self.regex_help_btn.clicked.connect(self.show_regex_help)
        regex_test_layout.addWidget(self.regex_help_btn)
        regex_test_layout.addStretch()
        keyword_layout.addLayout(regex_test_layout)
        
        layout.addLayout(keyword_layout)
        
        self.regex_cb = QCheckBox("使用正则表达式匹配")
        self.regex_cb.setToolTip("勾选后，关键字将作为正则表达式使用")
        layout.addWidget(self.regex_cb)
        
        # 排除文本区域
        exclude_layout = QVBoxLayout()
        exclude_layout.addWidget(QLabel("排除文本（每行一个排除文本，命中其一即排除）:"))
        self.exclude_edit = QPlainTextEdit()
        self.exclude_edit.setMaximumHeight(80)
        self.exclude_edit.setPlaceholderText("每行一个排除文本")
        exclude_layout.addWidget(self.exclude_edit)
        layout.addLayout(exclude_layout)
        
        # 配置参数
        params_layout = QVBoxLayout()
        
        lines_layout = QHBoxLayout()
        lines_layout.addWidget(QLabel("附近行数（-1表示不输出附近行）:"))
        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(-1, 100)  # 允许设置为-1
        self.lines_spin.setValue(self.config.get("nearby_lines", 2))
        self.lines_spin.setToolTip("设置为-1时不输出附近行内容，设置为0或正数时输出对应行数的附近内容")
        lines_layout.addWidget(self.lines_spin)
        params_layout.addLayout(lines_layout)
        
        chars_layout = QHBoxLayout()
        chars_layout.addWidget(QLabel("附近字符数:"))
        self.chars_spin = QSpinBox()
        self.chars_spin.setRange(0, 1000)
        self.chars_spin.setValue(self.config.get("nearby_chars", 20))
        chars_layout.addWidget(self.chars_spin)
        params_layout.addLayout(chars_layout)
        
        down_layout = QHBoxLayout()
        down_layout.addWidget(QLabel("向下行数:"))
        self.down_spin = QSpinBox()
        self.down_spin.setRange(-100, 100)
        self.down_spin.setValue(self.config.get("down_lines", 0))
        down_layout.addWidget(self.down_spin)
        params_layout.addLayout(down_layout)
        
        up_layout = QHBoxLayout()
        up_layout.addWidget(QLabel("向上行数:"))
        self.up_spin = QSpinBox()
        self.up_spin.setRange(-100, 100)
        self.up_spin.setValue(self.config.get("up_lines", 0))
        up_layout.addWidget(self.up_spin)
        params_layout.addLayout(up_layout)
        
        layout.addLayout(params_layout)
        
        # 选项复选框
        self.exclude_nearby_cb = QCheckBox("排除文本参与附近检查")
        self.exclude_nearby_cb.setChecked(True)
        layout.addWidget(self.exclude_nearby_cb)
        
        self.multi_line_cb = QCheckBox("多行关键字参与附近匹配过滤")
        self.multi_line_cb.setToolTip("勾选后，除第一行外的其他关键字如果在附近内容中出现，将排除该结果")
        layout.addWidget(self.multi_line_cb)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def restore_geometry(self):
        """恢复窗口大小"""
        geometry = self.settings.value("keyword_dialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # 默认大小
            self.resize(500, 600)
    
    def closeEvent(self, event):
        """窗口关闭时保存大小"""
        self.settings.setValue("keyword_dialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def get_keyword_data(self):
        """获取对话框中的数据"""
        # 修复：使用正确的分隔符分割关键字，避免+号被错误处理
        keyword_text = self.keyword_edit.toPlainText().strip()
        if not keyword_text:
            return None
            
        # 统一按行分割，不再使用逗号分隔（避免与正则表达式中的逗号冲突）
        words = [line.strip() for line in keyword_text.split('\n') if line.strip()]
        
        # 处理排除文本（统一按行分割，不再使用逗号分隔）
        exclude_text = self.exclude_edit.toPlainText().strip()
        if exclude_text:
            exclude = [line.strip() for line in exclude_text.split('\n') if line.strip()]
        else:
            exclude = []
        
        if words:
            # 获取备注信息
            remark = self.remark_edit.toPlainText().strip()
            
            return {
                "words": words,
                "exclude": exclude,
                "nearby_lines": self.lines_spin.value(),
                "nearby_chars": self.chars_spin.value(),
                "down_lines": self.down_spin.value(),
                "up_lines": self.up_spin.value(),
                "enabled": True,
                "exclude_nearby": self.exclude_nearby_cb.isChecked(),
                "multi_line_exclude": self.multi_line_cb.isChecked(),
                "use_regex": self.regex_cb.isChecked(),
                "remark": remark if remark else ""  # 保存备注信息
            }
        return None
    
    def show_regex_help(self):
        """显示正则表达式语法说明"""
        # 如果已经存在帮助窗口且窗口仍然有效，则激活它
        if RegexHelpDialog._instance is not None:
            help_dialog = RegexHelpDialog._instance
            # 检查窗口是否仍然存在且可见
            if help_dialog.isVisible():
                help_dialog.raise_()
                help_dialog.activateWindow()
            else:
                # 窗口已关闭但引用未清除，创建新窗口
                RegexHelpDialog._instance = None
                help_dialog = RegexHelpDialog(self)
                help_dialog.show()
        else:
            # 创建新的帮助窗口
            help_dialog = RegexHelpDialog(self)
            help_dialog.show()
    
    def test_regex(self):
        """测试正则表达式功能"""
        if not self.regex_cb.isChecked():
            QMessageBox.information(self, "提示", "请先勾选'使用正则表达式匹配'来测试正则表达式")
            return
            
        keyword_text = self.keyword_edit.toPlainText().strip()
        if not keyword_text:
            QMessageBox.warning(self, "警告", "请输入要测试的正则表达式")
            return
        
        # 测试对话框
        test_dialog = RegexTestDialog(self, keyword_text)
        test_dialog.exec_()

class RegexTestDialog(QDialog):
    """正则表达式测试对话框"""
    
    def __init__(self, parent=None, regex_pattern=""):
        super().__init__(parent)
        self.settings = QSettings("CongSec", "TextProcessor")
        self.setWindowTitle("测试正则表达式")
        self.setModal(True)
        self.regex_pattern = regex_pattern
        self.init_ui()
        # 恢复窗口大小
        self.restore_geometry()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 正则表达式输入
        regex_layout = QVBoxLayout()
        regex_label_layout = QHBoxLayout()
        regex_label_layout.addWidget(QLabel("正则表达式:"))
        # 添加问号帮助按钮
        self.regex_help_btn = QPushButton("?")
        self.regex_help_btn.setMaximumWidth(30)
        self.regex_help_btn.setToolTip("点击查看正则表达式语法说明")
        self.regex_help_btn.clicked.connect(self.show_regex_help)
        regex_label_layout.addWidget(self.regex_help_btn)
        regex_label_layout.addStretch()
        regex_layout.addLayout(regex_label_layout)
        self.regex_edit = QPlainTextEdit()
        self.regex_edit.setMaximumHeight(60)
        self.regex_edit.setPlainText(self.regex_pattern)
        regex_layout.addWidget(self.regex_edit)
        layout.addLayout(regex_layout)
        
        # 测试文本输入
        test_text_layout = QVBoxLayout()
        test_text_layout.addWidget(QLabel("测试文本:"))
        self.test_text_edit = QPlainTextEdit()
        self.test_text_edit.setMaximumHeight(100)
        self.test_text_edit.setPlaceholderText("请输入要测试的文本...")
        test_text_layout.addWidget(self.test_text_edit)
        layout.addLayout(test_text_layout)
        
        # 测试按钮
        test_btn_layout = QHBoxLayout()
        self.test_btn = QPushButton("测试匹配")
        self.test_btn.clicked.connect(self.test_matching)
        test_btn_layout.addWidget(self.test_btn)
        test_btn_layout.addStretch()
        layout.addLayout(test_btn_layout)
        
        # 结果显示
        result_layout = QVBoxLayout()
        result_layout.addWidget(QLabel("匹配结果:"))
        self.result_edit = QPlainTextEdit()
        self.result_edit.setReadOnly(True)
        self.result_edit.setMaximumHeight(150)
        result_layout.addWidget(self.result_edit)
        layout.addLayout(result_layout)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def restore_geometry(self):
        """恢复窗口大小"""
        geometry = self.settings.value("regex_test_dialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # 默认大小
            self.setGeometry(100, 100, 600, 400)
    
    def closeEvent(self, event):
        """窗口关闭时保存大小"""
        self.settings.setValue("regex_test_dialog/geometry", self.saveGeometry())
        super().closeEvent(event)
    
    def test_matching(self):
        """测试正则表达式匹配"""
        regex_pattern = self.regex_edit.toPlainText().strip()
        test_text = self.test_text_edit.toPlainText()
        
        if not regex_pattern:
            QMessageBox.warning(self, "警告", "请输入正则表达式")
            return
        
        try:
            # 编译正则表达式
            pattern = re.compile(regex_pattern)
            
            # 进行匹配测试
            matches = list(pattern.finditer(test_text))
            
            if not matches:
                self.result_edit.setPlainText("未找到匹配项")
                return
            
            # 显示匹配结果
            result_lines = []
            result_lines.append(f"找到 {len(matches)} 个匹配项:")
            result_lines.append("-" * 40)
            
            for i, match in enumerate(matches, 1):
                result_lines.append(f"匹配项 {i}:")
                result_lines.append(f"  匹配文本: '{match.group()}'")
                result_lines.append(f"  起始位置: {match.start()}")
                result_lines.append(f"  结束位置: {match.end()}")
                
                # 显示捕获组
                if match.groups():
                    result_lines.append(f"  捕获组: {match.groups()}")
                
                result_lines.append("")
            
            self.result_edit.setPlainText("\n".join(result_lines))
            
        except re.error as e:
            self.result_edit.setPlainText(f"正则表达式错误: {str(e)}")
        except Exception as e:
            self.result_edit.setPlainText(f"测试过程中出错: {str(e)}")
    
    def show_regex_help(self):
        """显示正则表达式语法说明"""
        # 如果已经存在帮助窗口且窗口仍然有效，则激活它
        if RegexHelpDialog._instance is not None:
            help_dialog = RegexHelpDialog._instance
            # 检查窗口是否仍然存在且可见
            if help_dialog.isVisible():
                help_dialog.raise_()
                help_dialog.activateWindow()
            else:
                # 窗口已关闭但引用未清除，创建新窗口
                RegexHelpDialog._instance = None
                help_dialog = RegexHelpDialog(self)
                help_dialog.show()
        else:
            # 创建新的帮助窗口
            help_dialog = RegexHelpDialog(self)
            help_dialog.show()

class AddKeywordDialog(KeywordDialog):
    """添加关键字对话框"""
    def __init__(self, parent=None, config=None):
        super().__init__(parent, "添加关键字", config)

class EditKeywordDialog(KeywordDialog):
    """编辑关键字对话框"""
    def __init__(self, parent=None, keyword_data=None, config=None):
        super().__init__(parent, "编辑关键字", config)
        if keyword_data:
            self.load_keyword_data(keyword_data)
    
    def load_keyword_data(self, keyword_data):
        """加载关键字数据到对话框"""
        self.remark_edit.setPlainText(keyword_data.get("remark", ""))  # 加载备注信息
        self.keyword_edit.setPlainText("\n".join(keyword_data.get("words", [])))
        self.exclude_edit.setPlainText("\n".join(keyword_data.get("exclude", [])))
        self.lines_spin.setValue(keyword_data.get("nearby_lines", self.config.get("nearby_lines", 2)))
        self.chars_spin.setValue(keyword_data.get("nearby_chars", self.config.get("nearby_chars", 20)))
        self.down_spin.setValue(keyword_data.get("down_lines", self.config.get("down_lines", 0)))
        self.up_spin.setValue(keyword_data.get("up_lines", self.config.get("up_lines", 0)))
        self.exclude_nearby_cb.setChecked(keyword_data.get("exclude_nearby", True))
        self.multi_line_cb.setChecked(keyword_data.get("multi_line_exclude", False))
        self.regex_cb.setChecked(keyword_data.get("use_regex", False))

class RegexHelpDialog(QDialog):
    """正则表达式语法说明对话框"""
    # 类变量，用于跟踪已打开的帮助窗口实例
    _instance = None
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("CongSec", "TextProcessor")
        self.setWindowTitle("正则表达式语法说明")
        self.setModal(False)  # 改为非模态，允许同时操作其他窗口
        self.init_ui()
        # 恢复窗口大小
        self.restore_geometry()
        
        # 保存实例引用
        RegexHelpDialog._instance = self
    
    def restore_geometry(self):
        """恢复窗口大小"""
        geometry = self.settings.value("regex_help_dialog/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # 默认大小
            self.setGeometry(100, 100, 700, 600)
    
    def closeEvent(self, event):
        """关闭窗口时清除实例引用并保存窗口大小"""
        self.settings.setValue("regex_help_dialog/geometry", self.saveGeometry())
        RegexHelpDialog._instance = None
        super().closeEvent(event)
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 使用QTextBrowser显示格式化的帮助文本
        help_text = QTextBrowser()
        help_text.setReadOnly(True)
        monospace_font = QFont("Consolas", 9)
        help_text.setFont(monospace_font)
        
        # 正则表达式语法说明内容
        help_content = """
<h2>正则表达式语法说明</h2>

<h3>一、基本字符匹配</h3>
<ul>
<li><b>普通字符</b>：直接匹配字符本身，如 <code>abc</code> 匹配 "abc"</li>
<li><b>.</b>：匹配除换行符外的任意单个字符，如 <code>a.c</code> 匹配 "abc"、"a1c" 等</li>
<li><b>\\</b>：转义字符，用于匹配特殊字符，如 <code>\\.</code> 匹配 "."</li>
</ul>

<h3>二、字符类</h3>
<ul>
<li><b>[abc]</b>：匹配方括号内的任意一个字符，如 <code>[abc]</code> 匹配 "a"、"b" 或 "c"</li>
<li><b>[^abc]</b>：匹配不在方括号内的任意字符，如 <code>[^abc]</code> 匹配除 "a"、"b"、"c" 外的字符</li>
<li><b>[a-z]</b>：匹配指定范围内的字符，如 <code>[a-z]</code> 匹配任意小写字母</li>
<li><b>\\d</b>：匹配数字，等价于 <code>[0-9]</code></li>
<li><b>\\D</b>：匹配非数字，等价于 <code>[^0-9]</code></li>
<li><b>\\w</b>：匹配字母、数字、下划线，等价于 <code>[a-zA-Z0-9_]</code></li>
<li><b>\\W</b>：匹配非字母、数字、下划线</li>
<li><b>\\s</b>：匹配空白字符（空格、制表符、换行符等）</li>
<li><b>\\S</b>：匹配非空白字符</li>
</ul>

<h3>三、量词（重复匹配）</h3>
<ul>
<li><b>*</b>：匹配前面的字符0次或多次，如 <code>a*</code> 匹配 ""、"a"、"aa" 等</li>
<li><b>+</b>：匹配前面的字符1次或多次，如 <code>a+</code> 匹配 "a"、"aa" 等</li>
<li><b>?</b>：匹配前面的字符0次或1次，如 <code>a?</code> 匹配 "" 或 "a"</li>
<li><b>{n}</b>：匹配前面的字符恰好n次，如 <code>a{3}</code> 匹配 "aaa"</li>
<li><b>{n,}</b>：匹配前面的字符至少n次，如 <code>a{2,}</code> 匹配 "aa"、"aaa" 等</li>
<li><b>{n,m}</b>：匹配前面的字符至少n次，最多m次，如 <code>a{2,4}</code> 匹配 "aa"、"aaa"、"aaaa"</li>
</ul>

<h3>四、位置锚点</h3>
<ul>
<li><b>^</b>：匹配字符串的开始位置，如 <code>^abc</code> 匹配以 "abc" 开头的字符串</li>
<li><b>$</b>：匹配字符串的结束位置，如 <code>abc$</code> 匹配以 "abc" 结尾的字符串</li>
<li><b>\\b</b>：匹配单词边界，如 <code>\\bword\\b</code> 匹配独立的单词 "word"</li>
</ul>

<h3>五、分组和捕获</h3>
<ul>
<li><b>(...)</b>：分组，捕获匹配的内容，如 <code>(abc)+</code> 匹配 "abc"、"abcabc" 等</li>
<li><b>(?:...)</b>：非捕获分组，不捕获匹配的内容</li>
<li><b>|</b>：或运算符，如 <code>a|b</code> 匹配 "a" 或 "b"</li>
</ul>

<h3>六、常用示例</h3>
<ul>
<li><b>匹配邮箱</b>：<code>[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]+</code></li>
<li><b>匹配手机号</b>：<code>1[3-9]\\d{9}</code></li>
<li><b>匹配IP地址</b>：<code>\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}</code></li>
<li><b>匹配URL</b>：<code>https?://[\\w\\.-]+(?:/[\\w\\.-]*)*</code></li>
<li><b>匹配数字</b>：<code>\\d+</code> 或 <code>[0-9]+</code></li>
<li><b>匹配中文</b>：<code>[\\u4e00-\\u9fa5]+</code></li>
</ul>

<h3>七、注意事项</h3>
<ul>
<li>在Python中，正则表达式字符串需要使用原始字符串（r"..."）或双反斜杠转义</li>
<li>特殊字符需要转义：<code>. * + ? ^ $ [ ] { } ( ) | \\</code></li>
<li>默认情况下，<code>.</code> 不匹配换行符，如需匹配可使用 <code>re.DOTALL</code> 标志</li>
<li>正则表达式默认区分大小写，如需忽略大小写可使用 <code>re.IGNORECASE</code> 标志</li>
</ul>
"""
        help_text.setHtml(help_content)
        layout.addWidget(help_text)
        
        # 关闭按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)