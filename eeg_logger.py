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
        self.thread = None
        self.stop_event = threading.Event()
        self.current_filename = "EEG_data" # 默认文件名
        
        # 初始化时就确定好保存路径，避免每次start_recording都新建
        self._setup_folder()

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

    def start_recording(self, filename):
        """
        开始录制单首歌曲的数据
        :param filename: 保存的文件名（不含扩展名）
        """
        if self.is_recording:
            logger.warning("Recording already in progress, restarting...")
            self.stop_recording()
            
        # self._setup_folder() # 移除此行，不再每次都创建新文件夹
        self.current_filename = filename
        self.stop_event.clear()
        self.is_recording = True
        
        self.thread = threading.Thread(target=self._record_loop)
        self.thread.daemon = True
        self.thread.start()
        logger.info(f"EEG recording started for: {filename}")

    def stop_recording(self):
        """停止录制并保存文件"""
        if not self.is_recording:
            return
            
        logger.info("Stopping EEG recording...")
        self.is_recording = False
        self.stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            
        logger.info("EEG recording stopped")

    def _record_loop(self):
        """录制线程主循环"""
        # logger.info("Resolving EEG stream...")
        streams = resolve_stream('type', 'EEG')
        if not streams:
            logger.error("No EEG stream found! Make sure BLE device is connected.")
            return
            
        # 按照 xw_web_C8.py 设置 max_chunklen=10
        inlet = StreamInlet(streams[0], max_chunklen=10)
        # logger.info("EEG stream connected. Capturing data...")
        
        eeg_buffer = []
        # start_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                # 尝试获取数据
                chunk, timestamps = inlet.pull_chunk(timeout=1.0)
                if chunk:
                    # logger.info(f"Received chunk size: {len(chunk)}") # 调试用，过于频繁可注释
                    eeg_buffer.extend(chunk)
                else:
                    # 记录空数据情况，但不要太频繁
                    if int(time.time()) % 5 == 0: 
                        logger.debug("No data received from LSL stream...")
                
                # 不再分片保存，全部暂存内存（假设单首歌数据量可控）
                # 如果担心内存，可以改为追加写入文件
                    
            except Exception as e:
                logger.error(f"Error in EEG recording loop: {e}")
                # 防止错误导致死循环占用CPU
                time.sleep(0.1)
                
        # 循环结束，一次性保存所有数据
        if eeg_buffer:
            self._save_to_file(eeg_buffer)

    def _save_to_file(self, data):
        """保存完整数据到文件"""
        if not data:
            return
            
        try:
            # 参考 xw_web_C8.py 的处理：除以 120
            arr = np.array(data) / 120.0
            
            # 构造完整路径
            # 格式要求：体现歌曲类别
            full_filename = f"{self.current_filename}.csv"
            filepath = os.path.join(self.save_path, full_filename)
            
            # 保存
            pd.DataFrame(arr).to_csv(filepath)
            
            logger.info(f"Saved EEG data to {filepath} (shape: {arr.shape})")
        except Exception as e:
            logger.error(f"Failed to save data: {e}")

    def _save_chunk(self, data, index):
        """(Deprecated)"""
        pass

    def _merge_data(self):
        """(Deprecated)"""
        pass
