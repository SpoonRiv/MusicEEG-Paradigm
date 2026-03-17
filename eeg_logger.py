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
        self.stop_event = threading.Event()
        self.data_lock = threading.Lock() # 数据访问锁
        self.current_filename = "EEG_data" # 默认文件名
        self.buffer = []
        self.inlet = None
        self.session_index = 0
        self.session_chunk_count = 0
        self.session_sample_count = 0
        self.bg_chunk_counter = 0
        self.last_chunk_log_time = 0.0
        self.last_data_time = 0.0
        self.no_data_reconnect_sec = 1.5
        
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
            
        with self.data_lock:
            self.session_index += 1
            self.current_filename = filename
            self.buffer = [] # 清空缓存
            self.is_recording = True
            self.start_time = time.time() # 记录开始时间
            self.session_chunk_count = 0
            self.session_sample_count = 0
            self.last_data_time = self.start_time
        
        if self.inlet is None:
            logger.warning("EEG Stream not connected yet! Data may be lost.")
        
        logger.info(
            f"EEG recording started for: {filename} | session={self.session_index} | save_path={self.save_path}"
        )

    def _select_best_stream(self, streams):
        """从候选流中选择最可能是当前BLE推送的EEG流。"""
        if not streams:
            return None
        candidates = []
        for stream in streams:
            score = 0
            if stream.type() == "EEG":
                score += 10
            if stream.name() == "TestStream":
                score += 5
            if stream.source_id() == "my EEG device":
                score += 5
            candidates.append((score, stream.created_at(), stream))
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidates[0][2]

    def _connect_inlet(self):
        """解析并连接LSL流，返回是否连接成功。"""
        streams = resolve_stream('type', 'EEG')
        best_stream = self._select_best_stream(streams)
        if best_stream is None:
            return False
        self.inlet = StreamInlet(best_stream, max_chunklen=10)
        logger.info(
            "EEG stream connected. "
            f"name={best_stream.name()} | type={best_stream.type()} | "
            f"channels={best_stream.channel_count()} | source_id={best_stream.source_id()} | "
            f"created_at={best_stream.created_at():.3f}"
        )
        return True

    def stop_recording(self):
        """停止录制并异步保存文件 (线程安全)"""
        data_to_save = []
        duration = 0
        save_filename = ""

        with self.data_lock:
            if not self.is_recording:
                return
                
            logger.info("Stopping EEG recording...")
            self.is_recording = False
            duration = time.time() - self.start_time
            save_filename = self.current_filename
            
            # 获取数据副本
            if self.buffer:
                data_to_save = list(self.buffer)
                self.buffer = [] # 立即清空
            logger.info(
                f"Stop summary | session={self.session_index} | filename={save_filename} | "
                f"chunks={self.session_chunk_count} | samples={self.session_sample_count} | "
                f"buffered_samples={len(data_to_save)} | duration={duration:.2f}s"
            )
        
        # 异步保存数据，不阻塞主线程
        if data_to_save:
            threading.Thread(
                target=self._save_to_file,
                args=(data_to_save, duration, save_filename)
            ).start()
        else:
            logger.warning(
                f"No data recorded to save | session={self.session_index} | filename={save_filename}"
            )
            
        logger.info("EEG recording stopped (Save task submitted)")

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
                    if self._connect_inlet():
                        self.last_data_time = time.time()
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
                if chunk:
                    chunk_len = len(chunk)
                    self.bg_chunk_counter += 1
                    self.last_data_time = time.time()
                    session_samples = 0
                    buffer_len = 0
                    with self.data_lock:
                        if self.is_recording:
                            self.session_chunk_count += 1
                            self.session_sample_count += chunk_len
                            self.buffer.extend(chunk)
                            session_samples = self.session_sample_count
                            buffer_len = len(self.buffer)
                    now = time.time()
                    if self.is_recording and (
                        self.bg_chunk_counter % 50 == 0 or now - self.last_chunk_log_time >= 5
                    ):
                        self.last_chunk_log_time = now
                        logger.info(
                            f"EEG chunk received | chunk_samples={chunk_len} | "
                            f"session={self.session_index} | session_samples={session_samples} | "
                            f"buffer_len={buffer_len}"
                        )
                elif self.is_recording and time.time() - self.last_data_time > self.no_data_reconnect_sec:
                    logger.warning(
                        f"No EEG chunk for {self.no_data_reconnect_sec:.1f}s while recording, reconnecting inlet..."
                    )
                    self.inlet = None
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
            file_size = os.path.getsize(filepath)
            
            samples = len(data)
            msg = f"Saved EEG data to {filepath} (shape: {arr.shape}, bytes: {file_size})"
            
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
