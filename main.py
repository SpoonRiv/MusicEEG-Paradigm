# -*- coding: utf-8 -*-
"""
主程序入口模块
集成各个模块，实现主界面逻辑。
"""

import sys
import os
import logging
from typing import List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QMessageBox, QGroupBox, QGridLayout,
    QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon

# 导入 pygame 用于音频播放
import pygame

# 导入自定义模块
import styles
from ble_worker import BLEWorker
from lyrics_window import LyricsWindow
from ui_components import SongCard
from eeg_logger import EEGLogger

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='experiment_log.txt',
    filemode='a'
)
logger = logging.getLogger("Main")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music-EEG Experiment Controller")
        self.resize(1200, 800) 
        
        # 路径配置
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.music_dir = os.path.join(self.base_dir, "Musics")
        self.lyrics_dir = os.path.join(self.base_dir, "Lyrics")
        
        # 设置窗口图标
        logo_path = os.path.join(self.base_dir, "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # 初始化 Pygame Mixer
        pygame.mixer.init()
        
        # 数据
        self.song_cards: List[SongCard] = []
        self.current_playlist = []
        self.current_song_index = 0
        self.is_playing = False
        self.ble_worker = None
        self.eeg_logger = EEGLogger(self.base_dir)
        
        # 应用样式
        self.setStyleSheet(styles.MAIN_STYLESHEET)
        
        # UI 初始化
        self.init_ui()
        self.load_songs()
        
        # 定时器用于检查播放状态
        self.play_timer = QTimer()
        self.play_timer.setInterval(100) # 100ms 检查一次
        self.play_timer.timeout.connect(self.check_playback_status)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局：水平分布 (左侧控制，右侧网格)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(30)
        
        # === 左侧控制面板 ===
        control_panel = QGroupBox("") # 去除标题 "控制面板"
        control_layout = QVBoxLayout()
        control_layout.setContentsMargins(20, 20, 20, 20)
        control_layout.setSpacing(25)
        
        # Logo
        logo_path = os.path.join(self.base_dir, "logo.png")
        if os.path.exists(logo_path):
            lbl_logo = QLabel()
            pixmap = QPixmap(logo_path)
            # 缩放 logo 以适应控制面板宽度 (例如 180px)
            scaled_pixmap = pixmap.scaledToWidth(180, Qt.TransformationMode.SmoothTransformation)
            lbl_logo.setPixmap(scaled_pixmap)
            lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            control_layout.addWidget(lbl_logo)

        # 标题
        lbl_title = QLabel("Music-EEG\nParadigm")
        lbl_title.setObjectName("lbl_title")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(lbl_title)
        
        control_layout.addSpacing(20)

        # 设备连接区
        dev_layout = QVBoxLayout()
        dev_layout.setSpacing(10)
        dev_layout.addWidget(QLabel("蓝牙设备名称"))
        self.device_input = QLineEdit("MSM")
        self.device_input.setPlaceholderText("输入设备名...")
        dev_layout.addWidget(self.device_input)
        control_layout.addLayout(dev_layout)
        
        self.btn_connect = QPushButton("连接设备")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.clicked.connect(self.connect_ble)
        control_layout.addWidget(self.btn_connect)
        
        self.lbl_status = QLabel("状态: 等待连接...")
        self.lbl_status.setObjectName("lbl_status")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.lbl_status)
        
        control_layout.addStretch()
        
        # 实验控制区
        self.btn_start = QPushButton("开始实验")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(70)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setEnabled(False) 
        self.btn_start.clicked.connect(self.start_experiment)
        control_layout.addWidget(self.btn_start)
        
        control_panel.setLayout(control_layout)
        control_panel.setFixedWidth(300)
        main_layout.addWidget(control_panel)
        
        # === 右侧内容区 ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 10, 0, 0)
        
        # 顶部工具栏
        toolbar = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.setFixedWidth(100)
        self.btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select_all.clicked.connect(self.select_all_songs)
        
        self.btn_deselect_all = QPushButton("全不选")
        self.btn_deselect_all.setFixedWidth(100)
        self.btn_deselect_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_deselect_all.clicked.connect(self.deselect_all_songs)
        
        # toolbar.addWidget(QLabel("实验歌单选择")) # 用户要求去除字样
        toolbar.addStretch()
        toolbar.addWidget(self.btn_select_all)
        toolbar.addWidget(self.btn_deselect_all)
        
        right_layout.addLayout(toolbar)
        
        # 歌曲网格
        # 用户要求：主窗口打开不要折叠内容，要一次性平铺所有的按钮
        # 移除 QScrollArea，直接使用 QWidget 容器，或者让 ScrollArea 足够大且无滚动条
        # 为了保险起见，保留 grid_container 但直接放入布局，或者使用 ScrollArea 但确保它扩展
        
        # 修改方案：直接将 grid_container 放入 right_layout，并设置 stretch
        grid_container = QWidget()
        self.grid_layout = QGridLayout(grid_container)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setContentsMargins(10, 10, 10, 10)
        
        # 将 grid_container 放入右侧布局，并给予最大比例
        right_layout.addWidget(grid_container, 1) # stretch=1
        
        # 移除 ScrollArea 相关代码
        # scroll = QScrollArea()
        # scroll.setWidgetResizable(True)
        # scroll.setFrameShape(QFrame.Shape.NoFrame)
        # scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # scroll.setWidget(grid_container)
        # right_layout.addWidget(scroll)
        
        main_layout.addWidget(right_panel, 1) # 让右侧区域占据更多空间

    def load_songs(self):
        """扫描目录加载歌曲"""
        if not os.path.exists(self.music_dir):
            os.makedirs(self.music_dir)
            
        files = os.listdir(self.music_dir)
        mp3_files = [f for f in files if f.lower().endswith('.mp3')]
        mp3_files.sort()
        
        # 清除现有卡片
        for card in self.song_cards:
            self.grid_layout.removeWidget(card)
            card.deleteLater()
        self.song_cards.clear()
        
        # 加载新卡片
        # 用户要求：把现在5*2的列表转置成2*5
        columns = 2 # 2列
        for idx, filename in enumerate(mp3_files):
            name = os.path.splitext(filename)[0]
            music_path = os.path.join(self.music_dir, filename)
            lyrics_path = os.path.join(self.lyrics_dir, name + ".txt")
            has_lyrics = os.path.exists(lyrics_path)
            
            song_data = {
                'id': idx + 1,
                'name': name,
                'music_path': music_path,
                'lyrics_path': lyrics_path if has_lyrics else None
            }
            
            card = SongCard(song_data)
            card.set_selected(True) # 默认选中
            # 允许卡片在网格中扩展
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.song_cards.append(card)
            
            row = idx // columns
            col = idx % columns
            self.grid_layout.addWidget(card, row, col)
            
        self.lbl_status.setText(f"已加载 {len(self.song_cards)} 首歌曲")

    def select_all_songs(self):
        for card in self.song_cards:
            card.set_selected(True)

    def deselect_all_songs(self):
        for card in self.song_cards:
            card.set_selected(False)

    def show_message(self, title, content, is_error=False):
        """显示自定义样式的弹窗（无图标）"""
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(content)
        msg.setIcon(QMessageBox.Icon.NoIcon) # 移除图标
        msg.exec()

    def connect_ble(self):
        device_name = self.device_input.text().strip()
        if not device_name:
            self.show_message("错误", "请输入设备名称", is_error=True)
            return
            
        self.btn_connect.setEnabled(False)
        self.lbl_status.setText("正在连接...")
        
        self.ble_worker = BLEWorker(device_name, self.base_dir)
        self.ble_worker.status_changed.connect(self.update_status)
        self.ble_worker.connection_success.connect(self.on_connection_result)
        self.ble_worker.start()

    def update_status(self, msg):
        self.lbl_status.setText(msg)
        logger.info(msg)

    def on_connection_result(self, success):
        self.btn_connect.setEnabled(True)
        if success:
            self.btn_start.setEnabled(True)
            self.btn_connect.setText("重新连接")
            self.show_message("成功", "设备连接成功！")
        else:
            self.btn_start.setEnabled(False)
            self.show_message("失败", "设备连接失败，请查看日志或重试。", is_error=True)

    def start_experiment(self):
        self.current_playlist = []
        for card in self.song_cards:
            if card.is_selected:
                self.current_playlist.append(card.song_data)
        
        if not self.current_playlist:
            self.show_message("提示", "请先选择至少一首歌曲")
            return
            
        # 按 ID 排序
        self.current_playlist.sort(key=lambda x: x['id'])
        self.current_song_index = 0
        
        # 创建并显示全屏窗口
        self.lyrics_window = LyricsWindow()
        self.lyrics_window.stop_signal.connect(self.on_experiment_aborted)
        
        # 开始记录 EEG
        if self.eeg_logger:
            self.eeg_logger.start_recording()
            
        self.lyrics_window.showFullScreen()
        
        QTimer.singleShot(1000, self.play_next_song)

    def on_experiment_aborted(self):
        """处理实验中断（用户按ESC）"""
        logger.info("Experiment aborted by user (ESC pressed)")
        self.play_timer.stop()
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
        self.is_playing = False
        
        # 发送结束 Trigger (可选，保持数据完整性)
        if self.ble_worker:
            self.ble_worker.send_trigger(0xFF) # 使用 0xFF 标记中断
            
        # 停止记录 EEG
        if self.eeg_logger:
            self.eeg_logger.stop_recording()

        self.show_message("中断", "实验已停止")

    def play_next_song(self):
        if self.current_song_index >= len(self.current_playlist):
            self.finish_experiment()
            return
            
        song = self.current_playlist[self.current_song_index]
        logger.info(f"Preparing to play: {song['name']} (ID: {song['id']})")
        
        # 1. 加载歌词
        lyrics_text = f"正在播放: {song['name']}..."
        if song['lyrics_path']:
            try:
                with open(song['lyrics_path'], 'r', encoding='utf-8') as f:
                    lyrics_text = f.read()
            except Exception as e:
                logger.error(f"Failed to read lyrics: {e}")
                lyrics_text = f"{song['name']}\n(读取歌词失败)"
        else:
            lyrics_text = f"{song['name']}\n(无歌词文件)"
            
        self.lyrics_window.set_text(lyrics_text)
        
        # 2. 发送 Trigger
        if self.ble_worker:
            trigger_val = song['id']
            self.ble_worker.send_trigger(trigger_val)
            logger.info(f"Trigger sent: {trigger_val}")
        
        # 3. 播放音乐
        try:
            pygame.mixer.music.load(song['music_path'])
            pygame.mixer.music.play()
            self.is_playing = True
            self.play_timer.start()
        except Exception as e:
            logger.error(f"Failed to play music: {e}")
            self.finish_experiment()

    def check_playback_status(self):
        if not pygame.mixer.music.get_busy() and self.is_playing:
            self.is_playing = False
            self.play_timer.stop()
            self.on_song_finished()

    def on_song_finished(self):
        logger.info(f"Song finished: {self.current_playlist[self.current_song_index]['name']}")
        
        if self.ble_worker:
            self.ble_worker.send_trigger(0xAA)
        
        self.current_song_index += 1
        QTimer.singleShot(2000, self.play_next_song)

    def finish_experiment(self):
        logger.info("Experiment finished")
        
        # 停止记录 EEG
        if self.eeg_logger:
            self.eeg_logger.stop_recording()
            
        if hasattr(self, 'lyrics_window'):
            self.lyrics_window.close()
        self.show_message("完成", "实验结束")

    def closeEvent(self, event):
        if hasattr(self, 'eeg_logger') and self.eeg_logger:
            self.eeg_logger.stop_recording()
            
        if self.ble_worker:
            self.ble_worker.stop()
            self.ble_worker.wait()
        pygame.mixer.quit()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
