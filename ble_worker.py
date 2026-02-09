# -*- coding: utf-8 -*-
"""
BLE 工作线程模块
负责在后台线程中处理蓝牙连接、扫描和数据通信。
使用 PyQt6 QThread 和 asyncio 事件循环。
"""

import asyncio
import logging
import os
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

try:
    from external_modules.ble_receive_eeg_trigger import BleReceiver
except ImportError:
    BleReceiver = None

logger = logging.getLogger("BLEWorker")

class BLEWorker(QThread):
    """
    后台线程，负责运行 asyncio 事件循环，处理 BLE 连接和通信
    """
    status_changed = pyqtSignal(str)  # 状态更新信号
    connection_success = pyqtSignal(bool) # 连接结果信号

    def __init__(self, device_name: str, log_path: str):
        super().__init__()
        self.device_name = device_name
        self.log_path = log_path
        self.loop = None
        self.receiver: Optional[BleReceiver] = None
        self.running = True
        self.connected = False

    def run(self):
        """线程入口"""
        if BleReceiver is None:
            self.status_changed.emit("错误: 无法导入 BleReceiver 模块")
            self.connection_success.emit(False)
            return

        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            self.status_changed.emit(f"正在初始化 BLE 接收器 (设备: {self.device_name})...")
            self.receiver = BleReceiver(self.device_name, self.log_path)
            
            self.status_changed.emit("正在扫描设备...")
            # 寻找设备
            found = self.receiver.get_ble_mac_address_specefic(max_retries=3)
            
            if not found:
                self.status_changed.emit("未找到设备，请检查设备是否开启")
                self.connection_success.emit(False)
                return

            self.status_changed.emit(f"设备已找到: {self.receiver.m_device_mac_address}")
            self.connected = True
            self.connection_success.emit(True)

            # 启动接收任务
            self.status_changed.emit("已连接，正在接收数据...")
            
            # 定义主任务，并发执行接收和初始化指令
            async def ble_main_task():
                # 启动接收任务 (这会阻塞直到 event 被 set)
                # 使用 create_task 让它在后台运行
                recv_task = asyncio.create_task(self.receiver.start_notification())
                
                # 等待连接建立
                # start_notification 内部会建立连接并赋值给 self.receiver.m_client
                max_retries = 50
                for _ in range(max_retries):
                    if self.receiver.m_client and self.receiver.m_client.is_connected:
                        break
                    await asyncio.sleep(0.2)
                
                if self.receiver.m_client and self.receiver.m_client.is_connected:
                    self.status_changed.emit("正在发送初始化指令...")
                    logger.info("Sending initialization commands...")
                    try:
                        await self.receiver.send_control_command(bytearray([0x02, 0x02]))
                        await asyncio.sleep(0.5)
                        
                        await self.receiver.send_control_command(bytearray([0x02, 0x01]))
                        logger.info("Initialization commands sent successfully")
                    except Exception as e:
                        logger.error(f"Failed to send init commands: {e}")
                        self.status_changed.emit(f"初始化指令发送失败: {e}")
                else:
                    logger.warning("Timeout waiting for BLE connection ready")

                # 等待接收任务结束
                await recv_task

            self.loop.run_until_complete(ble_main_task())
            
        except Exception as e:
            logger.error(f"BLE Error: {e}")
            self.status_changed.emit(f"BLE 错误: {str(e)}")
            self.connection_success.emit(False)
        finally:
            if self.loop:
                self.loop.close()

    def send_trigger(self, tag: int):
        """
        发送 Trigger 信号
        :param tag: 1-255 的整数
        """
        if not self.connected or not self.loop or not self.receiver:
            logger.warning("尝试发送 Trigger 但设备未连接")
            return

        data = bytearray([0xFF, tag])
        logger.info(f"Scheduling trigger send: {tag} (0x{tag:02X})")
        
        asyncio.run_coroutine_threadsafe(
            self.receiver.send_control_command(data), 
            self.loop
        )

    def stop(self):
        """停止线程"""
        self.running = False
        if self.receiver:
            self.receiver.is_receiving = False
            if hasattr(self.receiver, 'event'):
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(self.receiver.event.set)
