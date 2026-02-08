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

    def _setup_folder(self):
        """
        设置保存文件夹，自动编号
        仿照 xw_web_C8.py 的逻辑: offlinedata/EEGdata-{MMDD}-{index}
        """
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

    def start_recording(self):
        """开始录制"""
        if self.is_recording:
            logger.warning("Recording already in progress")
            return
            
        self._setup_folder()
        self.stop_event.clear()
        self.is_recording = True
        
        self.thread = threading.Thread(target=self._record_loop)
        self.thread.daemon = True
        self.thread.start()
        logger.info("EEG recording thread started")

    def stop_recording(self):
        """停止录制"""
        if not self.is_recording:
            return
            
        logger.info("Stopping EEG recording...")
        self.is_recording = False
        self.stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
            
        # 停止后尝试合并数据（模拟 EEG_merge 功能）
        self._merge_data()
        logger.info("EEG recording stopped")

    def _record_loop(self):
        """录制线程主循环"""
        logger.info("Resolving EEG stream...")
        streams = resolve_stream('type', 'EEG')
        if not streams:
            logger.error("No EEG stream found! Make sure BLE device is connected.")
            return
            
        # 按照 xw_web_C8.py 设置 max_chunklen=10
        inlet = StreamInlet(streams[0], max_chunklen=10)
        logger.info("EEG stream connected. Capturing data...")
        
        eeg_buffer = []
        file_index = 0
        start_time = time.time()
        
        while not self.stop_event.is_set():
            try:
                # 尝试获取数据
                chunk, timestamps = inlet.pull_chunk(timeout=1.0)
                if chunk:
                    eeg_buffer.extend(chunk)
                
                # 每30秒保存一次 (参考 xw_web_C8.py)
                current_time = time.time()
                if current_time - start_time >= 30:
                    self._save_chunk(eeg_buffer, file_index)
                    eeg_buffer = [] # 清空 buffer
                    file_index += 1
                    start_time = current_time
                    
            except Exception as e:
                logger.error(f"Error in EEG recording loop: {e}")
                # 防止错误导致死循环占用CPU
                time.sleep(0.1)
                
        # 循环结束，保存剩余数据
        if eeg_buffer:
            self._save_chunk(eeg_buffer, file_index)

    def _save_chunk(self, data, index):
        """保存数据分片"""
        if not data:
            return
            
        try:
            # 参考 xw_web_C8.py 的处理：除以 120
            # 注意：data 是 list of lists，可以直接转 numpy array
            arr = np.array(data) / 120.0
            
            filename = f"EEG-offline-data-{index}.csv"
            filepath = os.path.join(self.save_path, filename)
            
            # 使用默认参数保存 (index=True, header=True) 以匹配 xw_web_C8.py 行为
            # 如果原代码是不带 index 的，这里需要调整。
            # 原代码: pd.DataFrame(eeg_data).to_csv(...) -> 默认是带 index 和 header 的
            pd.DataFrame(arr).to_csv(filepath)
            
            logger.info(f"Saved chunk {index} to {filename} (shape: {arr.shape})")
        except Exception as e:
            logger.error(f"Failed to save chunk {index}: {e}")

    def _merge_data(self):
        """简单的合并功能，将分片文件合并为一个"""
        if not self.save_path:
            return
            
        try:
            files = [f for f in os.listdir(self.save_path) if f.startswith("EEG-offline-data-") and f.endswith(".csv")]
            if not files:
                return
                
            # 按序号排序
            # 假设文件名格式固定为 EEG-offline-data-{k}.csv
            files.sort(key=lambda x: int(x.split('-')[-1].split('.')[0]))
            
            logger.info(f"Merging {len(files)} files...")
            
            merged_filename = f"EEG-merged-{time.strftime('%H%M%S')}.csv"
            merged_path = os.path.join(self.save_path, merged_filename)
            
            # 读取第一个文件获取 header/index 格式
            first_df = pd.read_csv(os.path.join(self.save_path, files[0]), index_col=0)
            
            # 逐个读取并追加
            # 这种方式比较慢，但对于分片合并是安全的
            with open(merged_path, 'w', newline='') as outfile:
                # 先写入第一个文件
                first_df.to_csv(outfile) 
                
                # 后续文件跳过 header? 
                # pd.read_csv 读取时已经处理了 header
                # 实际上如果只是简单的拼接，可以直接用 pandas concat
                
            # 重写：使用 pandas concat
            df_list = []
            for f in files:
                p = os.path.join(self.save_path, f)
                # 假设都有 index 列
                df = pd.read_csv(p, index_col=0)
                df_list.append(df)
            
            if df_list:
                full_df = pd.concat(df_list, ignore_index=True)
                full_df.to_csv(merged_path)
                logger.info(f"Merged data saved to {merged_filename}")
                
        except Exception as e:
            logger.error(f"Merge failed: {e}")
