# -*- coding: utf-8 -*-
"""
UI 组件模块
定义了自定义的 UI 控件，如 SongCard。
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QCursor, QFont

import styles

class SongCard(QFrame):
    """
    歌曲卡片组件
    """
    clicked = pyqtSignal(object) # 发射 self

    def __init__(self, song_data, parent=None):
        super().__init__(parent)
        self.song_data = song_data
        self.is_selected = False
        self.setup_ui()

    def setup_ui(self):
        # 使用 MinimumSize 而不是 FixedSize，允许布局调整大小
        self.setMinimumSize(200, 100) 
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        # 阴影效果
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 歌名
        self.lbl_name = QLabel(self.song_data['name'])
        # 使用样式表设置字体，以避免被父控件的样式表覆盖，且不设置颜色以便继承父控件的颜色变化
        self.lbl_name.setStyleSheet("font-size: 28px; font-weight: bold; background-color: transparent; font-family: 'Microsoft YaHei';")
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_name)
        
        self.setLayout(layout)
        self.update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_selection()
            self.clicked.emit(self)

    def toggle_selection(self):
        self.is_selected = not self.is_selected
        self.update_style()

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.update_style()

    def update_style(self):
        if self.is_selected:
            self.setStyleSheet(styles.CARD_STYLE_SELECTED)
        else:
            self.setStyleSheet(styles.CARD_STYLE_NORMAL)
