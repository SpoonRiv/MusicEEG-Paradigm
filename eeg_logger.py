import os
import time
import threading
import logging
import pandas as pd
import numpy as np
from pylsl import StreamInlet, resolve_stream

# 配置日志
logger = logging.getLogger("EEGLogger")

class EEGLogger:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.save_path = None
        self.is_recording = False
        self.stop_requested = False # 新增停止请求标志
        self.stop_event = threading.Event()
        self.data_lock = threading.Lock() # 数据访问锁
        self.current_filename = "EEG_data" # 默认文件名
        self.buffer = []
        self.inlet = None
        
        # 初始化时就确定好保存路径，避免每次start_recording都新建
        self._setup_folder()
        
        # 启动后台数据采集线程
        self.bg_thread = threading.Thread(target=self._bg_loop)
        self.bg_thread.daemon = True
        self.bg_thread.start()

    def start_recording(self, filename):
        """
        开始录制单首歌曲的数据 (线程安全)
        :param filename: 保存的文件名（不含扩展名）
        """
        # 如果正在录制，先停止（会触发异步保存）
        if self.is_recording:
            logger.warning("Recording already in progress, restarting...")
            self.stop_recording()
            
        # 清空 inlet 中残留的旧数据，确保录制从当下开始
        if self.inlet:
            try:
                self.inlet.pull_chunk(timeout=0.0)
            except:
                pass

        with self.data_lock:
            self.current_filename = filename
            self.buffer = [] # 清空缓存
            self.is_recording = True
            self.stop_requested = False
            self.start_time = time.time() # 记录开始时间
        
        if self.inlet is None:
            logger.warning("EEG Stream not connected yet! Data may be lost.")
        
        logger.info(f"EEG recording started for: {filename}")

    def stop_recording(self):
        """发送停止录制请求，实际停止和保存由后台线程执行，确保不丢数据"""
        with self.data_lock:
            if not self.is_recording:
                return
            logger.info("Requesting stop recording...")
            self.stop_requested = True
            # 注意：不立即设为 False，等待后台线程处理最后一批数据


    def _bg_loop(self):
        """后台持续采集线程"""
        logger.info("Background EEG monitoring thread started.")
        
        while True:
            # 1. 确保流连接
            if self.inlet is None:
                try:
                    # resolve_stream 会阻塞直到找到流
                    # 这里是后台线程，阻塞是可以接受的
                    # logger.info("Waiting for EEG stream...")
                    streams = resolve_stream('type', 'EEG')
                    if streams:
                        self.inlet = StreamInlet(streams[0], max_chunklen=10)
                        logger.info("EEG stream connected.")
                    else:
                        time.sleep(1)
                except Exception as e:
                    logger.error(f"Stream resolution error: {e}")
                    time.sleep(1)
                continue
            
            # 2. 拉取数据
            try:
                # timeout设为较小值，保证循环响应速度
                chunk, timestamps = self.inlet.pull_chunk(timeout=0.2)
                
                # 无论是否有数据，都要检查是否需要停止，防止丢失最后一次的数据
                # 如果有数据，先存入
                if chunk:
                    with self.data_lock:
                        if self.is_recording:
                            self.buffer.extend(chunk)
                
                # 检查是否请求停止
                # 必须在处理完 chunk 之后检查
                stop_action_needed = False
                data_to_save = []
                duration = 0
                save_filename = ""
                
                with self.data_lock:
                    if self.is_recording and self.stop_requested:
                        # 执行停止逻辑
                        logger.info("Background thread handling stop request...")
                        self.is_recording = False
                        self.stop_requested = False
                        stop_action_needed = True
                        duration = time.time() - self.start_time
                        save_filename = self.current_filename
                        if self.buffer:
                            data_to_save = list(self.buffer)
                            self.buffer = []

                # 如果需要保存，在锁外执行（或者是启动新线程，避免阻塞 loop）
                if stop_action_needed:
                    if data_to_save:
                        # 启动线程保存，让 loop 继续跑（虽然 loop 接下来只是空转等待下次 start）
                        threading.Thread(
                            target=self._save_to_file,
                            args=(data_to_save, duration, save_filename)
                        ).start()
                    else:
                        logger.warning("No data recorded to save.")
                    logger.info("EEG recording fully stopped.")
                    
            except Exception as e:
                logger.error(f"Error pulling data: {e}")
                self.inlet = None # 触发重连
                time.sleep(0.5)

    def _setup_folder(self):
        """
        设置保存文件夹，自动编号
        仿照 xw_web_C8.py 的逻辑: offlinedata/EEGdata-{MMDD}-{index}
        """
        # 如果已经创建了文件夹，就不再创建
        if self.save_path and os.path.exists(self.save_path):
            return

        offline_dir = os.path.join(self.base_dir, 'offlinedata')
        if not os.path.exists(offline_dir):
            os.makedirs(offline_dir)
            
        current_time = time.strftime("%m%d", time.localtime())    
        folder_index = 1
        target_path = os.path.join(offline_dir, f"EEGdata-{current_time}-{folder_index}")
        
        # 检查文件夹是否存在且非空
        while os.path.exists(target_path) and os.listdir(target_path):
            folder_index += 1
            target_path = os.path.join(offline_dir, f"EEGdata-{current_time}-{folder_index}")
        
        self.save_path = target_path
        os.makedirs(self.save_path, exist_ok=True)
        logger.info(f"EEG data will be saved to: {self.save_path}")

    def _save_to_file(self, data, duration=None, filename=None):
        """保存完整数据到文件"""
        if not data:
            return
            
        try:
            # 参考 xw_web_C8.py 的处理：除以 120
            arr = np.array(data) / 120.0
            
            # 构造完整路径
            # 格式要求：体现歌曲类别
            # 如果未提供filename，使用当前的（可能不安全，但在stop_recording中已处理）
            fname = filename if filename else self.current_filename
            full_filename = f"{fname}.csv"
            filepath = os.path.join(self.save_path, full_filename)
            
            # 保存
            pd.DataFrame(arr).to_csv(filepath)
            
            samples = len(data)
            msg = f"Saved EEG data to {filepath} (shape: {arr.shape})"
            
            if duration and duration > 0:
                rate = samples / duration
                msg += f". Duration: {duration:.2f}s, Effective Rate: {rate:.2f} Hz"
                
            logger.info(msg)
        except Exception as e:
            logger.error(f"Failed to save data: {e}")

    def _save_chunk(self, data, index):
        """(Deprecated)"""
        pass

    def _merge_data(self):
        """(Deprecated)"""
        pass