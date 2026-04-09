# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
from PyQt5.QtCore import Qt
from syntax_highlighter import ResultHighlighter

class FullscreenResultWindow(QDialog):
    def __init__(self, parent=None, text="", title="全屏结果"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowState(Qt.WindowMaximized)
        layout = QVBoxLayout(self)
        self.text_edit = QTextBrowser()
        self.text_edit.setPlainText(text)
        self.text_edit.setReadOnly(True)
        self.highlighter = ResultHighlighter(self.text_edit.document())
        layout.addWidget(self.text_edit)
        btn_layout = QHBoxLayout()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)