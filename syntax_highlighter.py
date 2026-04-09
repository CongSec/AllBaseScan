# -*- coding: utf-8 -*-
import re
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCharFormat, QColor, QSyntaxHighlighter, QFont

class ResultHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighting_rules = []
        self.compiled_patterns = {}
        keyword_format = QTextCharFormat()
        keyword_format.setBackground(QColor(255, 255, 0))
        self.highlighting_rules.append((re.compile(r"关键字列表: (.+)"), keyword_format))
        match_format = QTextCharFormat()
        match_format.setBackground(QColor(255, 255, 0))
        self.highlighting_rules.append((re.compile(r"匹配到 \d+ 个关键字列表"), match_format))
        file_format = QTextCharFormat()
        file_format.setForeground(QColor(0, 0, 255))
        file_format.setFontWeight(75)
        self.highlighting_rules.append((re.compile(r"文件路径: .+"), file_format))
        self.highlighting_rules.append((re.compile(r"文件名: .+"), file_format))
        label_format = QTextCharFormat()
        label_format.setBackground(QColor(255, 255, 200))
        labels = [r"附近行内容:", r"附近文字:", r"文件:", r"-{50}", r"排除文本:", r"向下行内容:", r"向上行内容:", r"排除文本匹配区域:", r"排除文本匹配内容:"]
        for label in labels:
            self.highlighting_rules.append((re.compile(label), label_format))
        exclude_format = QTextCharFormat()
        exclude_format.setBackground(QColor(255, 200, 200))
        # 匹配包含[已排除:的行
        self.highlighting_rules.append((re.compile(r".*\[已排除:.*\]"), exclude_format))

    def highlightBlock(self, text):
        for pattern, fmt in self.highlighting_rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)

    def highlight_keywords(self, keywords, text):
        try:
            pattern_key = "|".join(re.escape(kw) for kw in keywords if kw)
            if pattern_key not in self.compiled_patterns:
                self.compiled_patterns[pattern_key] = re.compile(pattern_key)
            pattern = self.compiled_patterns[pattern_key]
            keyword_format = QTextCharFormat()
            keyword_format.setBackground(QColor(255, 255, 0))
            keyword_format.setFontWeight(QFont.Bold)
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, keyword_format)
        except Exception:
            pass