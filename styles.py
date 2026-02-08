# -*- coding: utf-8 -*-
"""
样式定义模块
定义了应用程序的配色方案、字体和 QSS 样式表。
采用沉稳的深色调设计 (Dark Theme)。
"""

from PyQt6.QtGui import QColor

# 颜色常量 (进一步调整：文字变白，橙色变浅，边框明显)
COLOR_BACKGROUND = "#202020"      # 主窗口背景：深灰
COLOR_PANEL = "#2D2D2D"           # 面板/卡片背景：稍亮灰
COLOR_BORDER = "#606060"          # 分割线/边框：更明显的灰色 (原#383838)
COLOR_ACCENT = "#FFB300"          # 核心强调/开始按钮：琥珀黄 (恢复为原色)
COLOR_TEXT_PRIMARY = "#FFFFFF"    # 一级文字：纯白 (原#B0B0B0)
COLOR_TEXT_SECONDARY = "#FFFFFF"  # 二级文字：纯白 (原#808080) - 用户要求所有灰色字变白

COLOR_STATUS_POSITIVE = "#8EBA43" # 积极：柔和橄榄绿
COLOR_STATUS_NEUTRAL = "#D47D5C"  # 中性：柔和砖红
COLOR_STATUS_NEGATIVE = "#5C95B5" # 消极：柔和蓝灰

COLOR_CARD_BG = "#2D2D2D"         # 卡片背景 (与Panel一致)
COLOR_CARD_HOVER = "#363636"      # 卡片悬停

COLOR_DISABLED = "#505050"        # 禁用/占位符

# 字体配置
FONT_FAMILY = "Microsoft YaHei"

# QSS 样式表
MAIN_STYLESHEET = f"""
    QMainWindow {{
        background-color: {COLOR_BACKGROUND};
    }}

    QWidget {{
        font-family: "{FONT_FAMILY}";
        font-size: 16px;
        color: {COLOR_TEXT_PRIMARY};
    }}

    /* 分组框样式 */
    QGroupBox {{
        background-color: {COLOR_PANEL};
        border: 2px solid {COLOR_BORDER}; /* 边框明显一点：2px */
        border-radius: 10px;
        margin-top: 10px; /* 不需要标题了，margin可以小一点 */
        padding-top: 15px;
    }}
    /* 隐藏 GroupBox 标题 */
    QGroupBox::title {{
        color: transparent;
        background-color: transparent;
        border: none;
    }}

    /* 按钮基础样式 */
    QPushButton {{
        background-color: {COLOR_ACCENT};
        color: #000000; /* 浅色背景用深色字 */
        border: none;
        border-radius: 8px;
        padding: 12px 24px;
        font-weight: bold;
        font-family: "{FONT_FAMILY}";
        font-size: 16px;
    }}
    QPushButton:hover {{
        background-color: #FFF3E0; /* 更浅 */
    }}
    QPushButton:pressed {{
        background-color: #FFCC80; /* 深一点 */
    }}
    QPushButton:disabled {{
        background-color: {COLOR_DISABLED};
        color: #A0A0A0;
    }}

    /* 特定按钮 */
    QPushButton#btn_connect {{
        background-color: {COLOR_ACCENT};
    }}
    
    QPushButton#btn_start {{
        background-color: {COLOR_ACCENT}; 
        font-size: 24px; /* 开始按钮更大 */
        border-radius: 10px;
    }}

    /* 输入框 */
    QLineEdit {{
        background-color: {COLOR_PANEL};
        border: 2px solid {COLOR_BORDER}; /* 边框明显 */
        border-radius: 6px;
        padding: 12px;
        color: {COLOR_TEXT_PRIMARY};
        font-family: "{FONT_FAMILY}";
        selection-background-color: {COLOR_ACCENT};
        selection-color: #000000;
    }}
    QLineEdit:focus {{
        border: 2px solid {COLOR_ACCENT};
    }}

    /* 标签 */
    QLabel {{
        color: {COLOR_TEXT_PRIMARY}; /* 全部白色 */
        font-family: "{FONT_FAMILY}";
    }}
    QLabel#lbl_title {{
        color: {COLOR_TEXT_PRIMARY};
        font-size: 28px;
        font-weight: bold;
    }}
    QLabel#lbl_status {{
        color: {COLOR_ACCENT};
        font-style: italic;
    }}

    /* 消息弹窗 QMessageBox */
    QMessageBox {{
        background-color: #FAFAFA; /* 浅色背景 */
        min-width: 200px; /* 设置最小宽度，防止换行 */
    }}
    QMessageBox QLabel {{
        color: #333333; /* 深色文字 */
        font-size: 18px;
        font-family: "{FONT_FAMILY}";
        min-width: 350px; /* 内容区域最小宽度 */
        min-height: 80px;
        qproperty-alignment: 'AlignVCenter | AlignHCenter'; /* 强制居中 */
        qproperty-wordWrap: true; /* 允许自动换行 */
    }}
    QMessageBox QPushButton {{
        background-color: {COLOR_ACCENT};
        color: #000000;
        border-radius: 6px;
        padding: 8px 30px; /* 按钮宽一点 */
        min-width: 100px;
        font-size: 14px;
    }}
    QMessageBox QPushButton:hover {{
        background-color: #FFCA28;
    }}
    QMessageBox QPushButton:pressed {{
        background-color: #FFB300;
    }}
"""

# 卡片样式
# Normal
CARD_STYLE_NORMAL = f"""
    QFrame {{
        background-color: {COLOR_CARD_BG};
        border-radius: 10px;
        border: 2px solid {COLOR_BORDER}; /* 边框明显：2px */
    }}
    QLabel {{
        color: {COLOR_TEXT_PRIMARY};
        background-color: transparent;
        border: none;
        font-family: "{FONT_FAMILY}";
    }}
"""

# Selected
CARD_STYLE_SELECTED = f"""
    QFrame {{
        background-color: {COLOR_ACCENT};
        border-radius: 10px;
        border: 2px solid {COLOR_ACCENT}; /* 选中时保持边框宽度一致，或者去掉 */
    }}
    QLabel {{
        color: #000000;
        font-weight: bold;
        background-color: transparent;
        border: none;
        font-family: "{FONT_FAMILY}";
    }}
"""
