# -*- coding: utf-8 -*-
"""
歌词展示窗口模块
定义了全屏展示歌词的窗口类。
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor

class LyricsWindow(QWidget):
    """
    全屏歌词展示窗口
    """
    # 定义停止信号
    stop_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Experiment")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint) # 无边框
        self.showFullScreen()
        
        # 黑色背景
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.black)
        self.setPalette(palette)
        
        layout = QVBoxLayout()
        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(False)
        
        # 设置字体 (80号字体，确保单行显示)
        font = QFont("Microsoft YaHei", 80, QFont.Weight.Bold)
        self.label.setFont(font)
        self.label.setStyleSheet("color: white;")
        
        layout.addWidget(self.label)
        self.setLayout(layout)

    def set_text(self, text):
        self.label.setText(text)
    
    def keyPressEvent(self, event):
        # 允许按 ESC 退出
        if event.key() == Qt.Key.Key_Escape:
            self.stop_signal.emit() # 发送停止信号
            self.close()
