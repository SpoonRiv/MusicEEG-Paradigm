#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (c) 2025 BUAA-BHB. All rights reserved.

Author: Duan Peidong & Jia Wenji
Created Date: 2025-05-04
Version: 1.5.4
Description: 
    脑电数据采集与处理主控程序
Change Log:
    1.5.4: 2026-02-03: Zhao Jinhao Corrected. 新增CORS支持
    1.5.3: 2026-02-03: Zhao Jinhao Corrected. 新增logo显示
    1.5.2: 2026-01-27: Zhao Jinhao Corrected. 新增电量显示
    1.5.1: 2025-12-01: Zhao Jinhao Corrected. 支持日志打印
    1.5.0: 2025-11-23: Zhao Jinhao Corrected. 新增在线功率谱密度计算功能
    1.4.2: 2025-06-09: Zhao Jinhao merged.
    1.4.1: 2025-06-06: Jia Wenji corrented. 脑电数据保存形式更改为每1分钟存储一次，并在停止保存时将所有数据串联
    1.4.0: 2025-06-04: Zhao Jinhao Corrected. 修改了长时间存储丢包、线程卡死的bug（最后放弃，使用1.4.1版本）
    1.3.3: 2025-05-13: Zhao Jinhao Corrected. 新增阻抗检测功能
    1.3.2: 2025-05-13: Zhao Jinhao Corrected. 使用带超时的阻塞式队列操作，平衡数据实时性和系统负载
    1.3.1: 2025-05-13: Zhao Jinhao Corrected. 输入框提示文字仅占位，不影响输入
    1.3.0: 2025-05-13: Zhao Jinhao Corrected. 存储csv文件时除以120，输出忽略掉warning
    1.2.0: 2025-05-09: Zhao Jinhao Corrected. 增加了波形显示功能，并且将其与数据采集线程分离，修改UI，修改存储路径及命名规则
    1.1.0: 2025-05-07: Zhao Jinhao Corrected. 每次无需创建新的日期子文件夹且自动编号，全部修改为相对路径
    1.0.0: 2025-05-04: 初始版本，实现基础数据采集与阻抗检测功能
"""

import multiprocessing
import os
from queue import Empty, Full
import shutil
import sys
import threading
import time
from EEG_merge import eeg_merge
from PyQt5 import QtCore, QtWebEngineWidgets, QtWidgets, QtGui
import numpy as np
import pandas as pd
from pylsl import StreamInlet, resolve_stream

try:
    from .ble_receive_eeg_trigger import breceive
except ImportError:
    from ble_receive_eeg_trigger import breceive

from ble_receive_impedance import impedance_receive
from save_edf import save_edf
from PSD_online import EEG_PSD_web_start
from QtUI.ui_styles import (
    BUTTON_BASE,
    BUTTON_STYLES,
    LINE_EDIT,
    MAIN_WINDOW,
    WAVEFORM_CONTAINER,
    BATTERY_LABEL,
)
from topomap_online import Web_start
from waveform_window import WaveformWindow

import warnings
warnings.filterwarnings("ignore")

def save_data(eeg_data,word,save_path,k):
    eeg_data = np.array(eeg_data) /120
    print("time: {}, 存储数据: {}, shape: {} ".format(time.time(), word, eeg_data.shape))
    pd.DataFrame(eeg_data).to_csv(os.path.join(save_path, "EEG-offline-data-{}.csv".format(k)))
    
def received_data(queue, save_path, display_queue: multiprocessing.Queue):
    # 采集脑电数据线程
    while True:
        streams = resolve_stream('type', 'EEG')
        inlet = StreamInlet(streams[0],max_chunklen=10)
        eeg_data = []
        word = queue.get()
        print("time: {}, 开始记录数据: {}".format(time.time(), word))
        k = 0
        start = time.time()
        if word.startswith("start"):
            print(1)
            while True:
                sample , timestamps= inlet.pull_chunk()
                eeg_data = eeg_data +sample
                # print(timestamps)
                current = time.time()
                if current - start >= 30:
                    print(current - start)
                    start = current
                    save_data(eeg_data,word,save_path,k)
                    eeg_data =[]
                    k += 1
                if display_queue is not None:
                    try:
                        # 非阻塞方式发送数据，如果队列满则丢弃旧数据
                        display_queue.put(np.array(eeg_data) / 120, block=False)
                        # print(np.array(eeg_data).shape)
                    except Full:
                        try:
                            # 队列满时，取出旧数据后再放入新数据
                            display_queue.get_nowait()
                            display_queue.put(np.array(eeg_data) / 120, block=False)
                            # print(np.array(eeg_data).shape)
                        except Empty:
                            pass
                    
                if not queue.empty():
                    end_word = queue.get()
                    # print(222222222222222)
                    if end_word == "end":
                        break
                    if end_word == "save":
                        eeg_data = []
            save_data(eeg_data,word,save_path,k)
        elif word == "del":
            print("存储脑电程序退出")
            break

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        # 获取当前日期和时间作为文件夹名称
        current_time = time.strftime("%m%d", time.localtime())    
        # 检查文件夹是否存在且非空时才自动编号
        folder_index = 1
        target_path = os.path.join('offlinedata', f"EEGdata-{current_time}-{folder_index}")
        while os.path.exists(target_path) and os.listdir(target_path):
            folder_index += 1
            target_path = os.path.join('offlinedata', f"EEGdata-{current_time}-{folder_index}")
        self.save_path = target_path
        # 创建文件夹
        os.makedirs(self.save_path, exist_ok=True)

        self.queue = multiprocessing.Queue()
        self.host = '127.0.0.1'
        self.port = 8866
        self.display_queue = multiprocessing.Queue(maxsize=1)
        self.shutdown_flag = threading.Event()
        self.is_open = False
        self.save_time = 0
        self.is_first = True
        self.is_save = False
        self.is_impedance = False
        self.is_preview = False
        self.impedance = None
        self.web = None
        self.is_PSD_online = 0
        self.psd_processor_instance = None
        
        MainWindow.setObjectName("BHB上位机")
        MainWindow.resize(1920, 1080)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        # 创建一个垂直布局来容纳按钮和波形显示
        main_layout = QtWidgets.QVBoxLayout(self.centralwidget)
        # 创建一个水平布局来放置按钮
        button_layout = QtWidgets.QHBoxLayout()
        self.lineEdit = QtWidgets.QLineEdit(self.centralwidget)
        self.lineEdit.setObjectName("lineEdit")

        self.pushButton1 = QtWidgets.QPushButton(self.centralwidget)
        # self.pushButton1.setGeometry(QtCore.QRect(790, 10, 90, 30))
        self.pushButton1.setObjectName("pushButton1")

        self.pushButton2 = QtWidgets.QPushButton(self.centralwidget)
        # self.pushButton2.setGeometry(QtCore.QRect(890, 10, 90, 30))
        self.pushButton2.setObjectName("pushButton2")

        self.pushButton3 = QtWidgets.QPushButton(self.centralwidget)
        # self.pushButton3.setGeometry(QtCore.QRect(990, 10, 130, 30))
        self.pushButton3.setObjectName("pushButton3")

        self.pushButton4 = QtWidgets.QPushButton(self.centralwidget)
        # self.pushButton4.setGeometry(QtCore.QRect(1130, 10, 90, 30))
        self.pushButton4.setObjectName("pushButton4")

        self.pushButton5 = QtWidgets.QPushButton(self.centralwidget)
        # self.pushButton5.setGeometry(QtCore.QRect(1230, 10, 90, 30))
        self.pushButton5.setObjectName("pushButton5")

        self.file_name = QtWidgets.QLineEdit(self.centralwidget)
        # self.file_name.setGeometry(QtCore.QRect(1330, 10, 180, 30))
        self.file_name.setObjectName("file_name")
        self.file_name.setFixedWidth(200)  # 设置固定宽度使其变窄
        
        self.battery_label = QtWidgets.QLabel(self.centralwidget)
        self.battery_label.setObjectName("battery_label")
        self.battery_label.setText("电量: --")
        self.battery_label.setMinimumWidth(100)
        self.battery_label.setAlignment(QtCore.Qt.AlignCenter)
        # 设置垂直方向固定，防止被布局拉伸
        self.battery_label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        # self.pushButton5 = QtWidgets.QPushButton(self.centralwidget)
        # self.pushButton5.setGeometry(QtCore.QRect(1230, 10, 90, 30))
        # self.pushButton5.setObjectName("pushButton4")

        button_layout.addWidget(self.lineEdit)
        # button_layout.addWidget(self.pushButton6)
        button_layout.addWidget(self.pushButton1)
        button_layout.addWidget(self.pushButton2)
        button_layout.addWidget(self.pushButton3)
        button_layout.addWidget(self.pushButton4)
        button_layout.addWidget(self.pushButton5)
        button_layout.addWidget(self.file_name)
        button_layout.addWidget(self.battery_label)

        main_layout.addLayout(button_layout)

        # 创建波形显示区域占位符
        self.waveform_container = QtWidgets.QWidget()
        main_layout.addWidget(self.waveform_container)
        
        # 设置布局的拉伸因子，使波形显示区域占据更多空间
        main_layout.setStretch(0, 1)  # 按钮区域
        main_layout.setStretch(1, 8)  # 波形显示区域

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1200, 23))
        self.menubar.setObjectName("menubar")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

        ## 创建web窗体
        self.qwebengine = QtWebEngineWidgets.QWebEngineView(MainWindow)
        self.qwebengine.setGeometry(20, 80, 1880, 840)
        # 配置WebEngine设置以允许跨域访问和本地文件访问
        settings = self.qwebengine.settings()
        settings.setAttribute(QtWebEngineWidgets.QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QtWebEngineWidgets.QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        self.qwebengine.hide()  # 默认隐藏，防止遮挡波形

        ## 创建连接
        # self.pushButton.clicked.connect(self.open_url)
        self.pushButton1.clicked.connect(self.ClickButton1)
        self.pushButton2.clicked.connect(self.ClickButton2)
        self.pushButton3.clicked.connect(self.ClickButton3)
        self.pushButton4.clicked.connect(self.ClickButton4)
        self.pushButton5.clicked.connect(self.ClickButton5)

        # 应用样式
        MainWindow.setStyleSheet(MAIN_WINDOW)
        
        # 为不同功能按钮应用不同样式
        self.pushButton1.setStyleSheet(BUTTON_BASE + BUTTON_STYLES['start'])
        self.pushButton2.setStyleSheet(BUTTON_BASE + BUTTON_STYLES['stop']) 
        self.pushButton3.setStyleSheet(BUTTON_BASE + BUTTON_STYLES['action'])
        self.pushButton4.setStyleSheet(BUTTON_BASE + BUTTON_STYLES['action'])
        self.pushButton5.setStyleSheet(BUTTON_BASE + BUTTON_STYLES['stop'])
        self.lineEdit.setStyleSheet(LINE_EDIT)
        self.file_name.setStyleSheet(LINE_EDIT)
        self.waveform_container.setStyleSheet(WAVEFORM_CONTAINER)
        self.battery_label.setStyleSheet(BATTERY_LABEL)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "BHB上位机"))
        
        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'logo.png')
        if os.path.exists(icon_path):
            MainWindow.setWindowIcon(QtGui.QIcon(icon_path))
            
        # 获取当前脚本所在目录的绝对路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # 拼接阻抗检测HTML文件的相对路径
        impedance_path = os.path.join(base_dir, 'templates', 'impedance_03.html')
        self.lineEdit.setText(_translate("MainWindow", f"file:///{impedance_path.replace(os.sep, '/')}"))
        # self.lineEdit.setText(_translate("MainWindow", r"file:///D:/ssvep/fenru/ex%20-%20%E5%89%AF%E6%9C%AC/%E6%97%A0%E4%BA%BA%E6%9C%BA/%E6%96%B0%E5%BB%BA%E6%96%87%E4%BB%B6%E5%A4%B9/class_ssvep_control_tello_left/templates/impedance.html"))
        self.pushButton1.setText(_translate("MainWindow", "开始采集EEG"))
        self.pushButton2.setText(_translate("MainWindow", "开始保存"))
        self.pushButton3.setText(_translate("MainWindow", "打开阻抗界面"))
        self.pushButton4.setText(_translate("MainWindow", "开始阻抗检测"))
        self.pushButton5.setText(_translate("MainWindow", "保存为edf"))
        self.file_name.setPlaceholderText(_translate("MainWindow", "请输入保存文件名"))  # 设置占位提示
        self.file_name.setText("")  # 清空初始文本

    def open_url(self):
        url=self.lineEdit.text()
        self.qwebengine.load(QtCore.QUrl(url))

    # def ClickButton1(self):
    #     ble_receive=threading.Thread(target=receive)
    #     ble_receive.daemon = True
    #     ble_receive.start()

    def ClickButton1(self):
        _translate = QtCore.QCoreApplication.translate
        # 新增网页关闭逻辑
        self.qwebengine.load(QtCore.QUrl('about:blank'))  # 加载空白页
        # self.qwebengine.page().deleteLater()  # 释放网页资源 (会导致后续无法加载)
        self.qwebengine.hide() # 隐藏网页视图
        
        self.battery_queue = multiprocessing.Queue()
        ble_receive=threading.Thread(target=breceive, args=(self.queue, self.host, self.port, "MSM", self.save_path, self.battery_queue))
        ble_receive.daemon = True
        ble_receive.start()
        
        # 启动电量更新定时器
        self.battery_timer = QtCore.QTimer()
        self.battery_timer.timeout.connect(self.update_battery)
        self.battery_timer.start(1000)  # 每秒更新一次
        
        while self.queue.empty():
            time.sleep(0.1)
        word = self.queue.get()
        print(word)
        time.sleep(1)
        if not self.is_preview:
            self.process = threading.Thread(target=received_data, args=(self.queue, self.save_path, self.display_queue))
            self.process.start()
            self.is_preview = True
            self.queue.put("start")
            self.pushButton1.setText(_translate("MainWindow", "预览模式"))
            print("开始预览波形")
            if not hasattr(self, 'waveform_window'):
                self.waveform_window = WaveformWindow(self.display_queue, self.waveform_container)
                if self.is_PSD_online:
                    # 启动带有Web服务的PSD处理
                    self.psd_processor_instance = EEG_PSD_web_start(self.display_queue, host='0.0.0.0', port=8878)
                    print(f"PSD Web service running on http://0.0.0.0:8878/ui")
                # 设置波形显示区域的大小策略
                self.waveform_window.setSizePolicy(
                    QtWidgets.QSizePolicy.Expanding,
                    QtWidgets.QSizePolicy.Expanding
                )
                # 将波形显示添加到容器中
                layout = QtWidgets.QVBoxLayout(self.waveform_container)
                layout.addWidget(self.waveform_window)

    def update_battery(self):
        """更新电量显示"""
        try:
            while not self.battery_queue.empty():
                level = self.battery_queue.get_nowait()
                # 假设电量数据是电压值(mV)或百分比，直接显示数值
                # 如果是电压，可能需要根据具体设备协议转换为百分比
                # 这里直接显示原始数值
                self.battery_label.setText(f"电量: {level}")
        except Exception:
            pass

    def ClickButton2(self):
        _translate = QtCore.QCoreApplication.translate
        if self.is_save:
            name = self.file_name.text().strip()
            # 过滤空输入和默认提示文本
            if not name or name == "请输入保存文件名":
                print("请输入有效文件名")
                return
            self.queue.put("end")
            self.pushButton2.setText(_translate("MainWindow", "开始保存"))
            print("停止保存")
            time.sleep(1)
            eeg_merge(self.save_path,name)
            self.is_save = False
        else:
            if self.is_first:
                if self.is_preview:
                    print("结束预览")
                    self.pushButton1.setText(_translate("MainWindow", "开始采集EEG"))
                    self.is_preview = False
                self.is_first = False
            self.pushButton2.setText(_translate("MainWindow", "停止保存"))
            # self.save_time = time.strftime("%m%d-%H%M%S", time.localtime()) 
            self.queue.put("save")
            self.save_time = time.strftime("%m%d-%H%M%S", time.localtime()) 
            print("开始保存")
            self.is_save = True

    def ClickButton3(self):
        _translate = QtCore.QCoreApplication.translate
        if self.is_open:
            self.shutdown_flag.set()
            self.web.join()
            self.is_open = False
            self.pushButton3.setText(_translate("MainWindow", "打开阻抗界面"))
            # 新增网页关闭逻辑
            self.qwebengine.load(QtCore.QUrl('about:blank'))  # 加载空白页
            # self.qwebengine.page().deleteLater()  # 释放网页资源
            self.qwebengine.hide() # 隐藏
            self.shutdown_flag.set()  # 触发关闭操作
        else:
            url=self.lineEdit.text()
            self.qwebengine.show() # 显示
            self.qwebengine.load(QtCore.QUrl(url))
            if not os.path.exists('offlinedata/impedance_cache'):
                os.makedirs('offlinedata/impedance_cache')
            shutil.rmtree('offlinedata/impedance_cache') 
            self.shutdown_flag.clear()
            self.web=threading.Thread(target=Web_start, args=(self.shutdown_flag ,))
            self.web.daemon = True
            self.is_open = True
            self.pushButton3.setText(_translate("MainWindow", "关闭阻抗界面"))
            self.web.start()

    def ClickButton4(self):
        _translate = QtCore.QCoreApplication.translate
        if self.is_impedance:
            self.queue.put("end")
            time.sleep(2)
            self.queue.put("del")
            self.impedance.join()
            self.pushButton4.setText(_translate("MainWindow", "开始阻抗检测"))
            self.is_impedance = False
        else:
            self.impedance=threading.Thread(target=impedance_receive , args=(self.queue ,))
            self.impedance.daemon = True
            self.impedance.start()
            time.sleep(25)
            # self.pushButton4.setText(_translate("MainWindow", "停止阻抗检测"))
            command = self.queue.get()
            print(command)
            if command.startswith("connected"):
                self.queue.put("start")
                self.pushButton4.setText(_translate("MainWindow", "停止阻抗检测"))
                self.is_impedance = True

    def ClickButton5(self):
        name = self.file_name.text().strip()
        # 过滤空输入和默认提示文本
        if not name or name == "请输入保存文件名":
            print("请输入有效文件名")
            return
        name = name + self.save_time
        print(name)
        save_edf(self.save_path,name)


if __name__ == '__main__':
    sys.argv.append("--disable-web-security")
    app = QtWidgets.QApplication(sys.argv)
    MainWindow = QtWidgets.QMainWindow()  # 创建窗体对象
    ui = Ui_MainWindow()  # 创建PyQt设计的窗体对象
    ui.setupUi(MainWindow)  # 调用窗体的方法对对象进行初始化设置

    # 获取屏幕列表
    screens = app.screens()
    if len(screens) > 1:  # 确保有多个显示器
        # 获取第二个显示器的几何信息
        screen_geometry = screens[1].geometry()
        # 将窗口移动到第二个显示器
        MainWindow.move(screen_geometry.x(), screen_geometry.y())

    MainWindow.showMaximized()  # 显示窗体
    sys.exit(app.exec_())  # 程序关闭时退出进程