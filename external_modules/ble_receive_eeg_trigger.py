#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (c) 2025 BUAA-BHB. All rights reserved.

Author: Jia Wenji
Created Date: 2025-03-10
Version: 1.2.2
Description: 
    蓝牙EEG数据接收模块，用于实时采集和保存EEG设备数据及trigger信号
Change Log:
    1.2.2: 2026-02-06: Zhao Jinhao Corrected. 修改了log输出默认关闭，需DEBUG_PRINT_ON=True开启
    1.2.1: 2026-01-27: Zhao Jinhao Corrected. 新增电量显示
    1.2.0: 2025-11-25: Zhao Jinhao Corrected. 过滤异常值，如果收到包长度140，清空缓存，防止错位
    1.1.4: 2025-11-25: Zhao Jinhao Corrected. 新增写日志功能，可在上位机开启LOG_ON，默认关闭
    1.1.3: 2025-11-14: Zhao Jinhao Corrected. 修bug
    1.1.2: 2025-10-15: Jia Wenji Corrected. 新增16导模式
    1.1.1: 2025-05-27: Zhao Jinhao Corrected. 添加if name == main
    1.1.0: 2025-05-11: Zhao Jinhao Corrected. 新增配置文件读取指定名称的BLE，添加重联机制
    1.0.0: 2025-03-10: 从线程启动改为独立启动，新增Socket通信接收trigger（原v2）
"""

import asyncio
import multiprocessing
import os
import socket
import threading
import time
import json
import logging

from bleak import BleakClient, BleakScanner
from jinja2.bccache import bc_magic
import numpy as np
import pandas as pd
from pylsl import StreamInfo, StreamOutlet
import scipy.io as sio
import configparser


DEBUG_PRINT_ON = False
LOG_ON = False
DEBUG_ON = False
SAMPLES_PER_FRAME = 5
TRIGGER_LENGTH = 1
CH_NUM = 8 + 1        # 8个通道 + 1个trigger通道
g_data_counter = 0
g_timer_begin = 0
g_timer_end = 0
raw_data = []


class BleReceiver:
    def __init__(self,device, log_file_path: str, battery_queue=None):
        self.word = ""
        self.channel_num = self.read_config_CHlen() - 1
        # self.channel_num = 8
        # CH_NUM = self.channel_num + 1
        self.data = np.empty((self.channel_num + 1, 0))
        self.is_receiving = True
        self.battery_queue = battery_queue
        # self.event = asyncio.Event()

        self.m_devices = None
        self.m_device_mac_address = None
        # self.channel_num = self.read_config_CHlen() - 1
        # print(device)
        self.m_device_name = device
        self.bci_ble_names = self.read_config()
        self.m_client = None
        self.m_client_serv = None
        self.info = StreamInfo(name='TestStream', type='EEG', channel_format='float32', channel_count=self.channel_num + 1, source_id='my EEG device')
        self.outlet = StreamOutlet(self.info)

        self.log_file_path = log_file_path
        if os.path.isdir(self.log_file_path):
            self.log_file_path = os.path.join(self.log_file_path, 'ble_receiver.log')
        
        self.logger = logging.getLogger(f'BleReceiver_{device}')
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            if LOG_ON:
                if log_dir and not os.path.exists(log_dir):
                    os.makedirs(log_dir, exist_ok=True)
                file_handler = logging.FileHandler(self.log_file_path, mode='a')
                formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            else:
                self.logger.addHandler(logging.NullHandler())

    def read_config(self):
        config = configparser.ConfigParser()
        config_name='external_modules/BHBconfig.ini'
        config.read(config_name, encoding='utf - 8')
        names_str = config.get("Bluetooth",'bci_ble_name')
        return [name.strip() for name in names_str.split(',')]

    # 扫描蓝牙设备
    async def find_ble_devices(self):
        if DEBUG_PRINT_ON:
            self.logger.info("Scanning ble devices...")
        self.m_devices = await BleakScanner.discover()
        if DEBUG_PRINT_ON:
            for dev in self.m_devices:
                if dev.rssi > -70:
                    print("\t-[", dev, dev.rssi, "]")

    # 获取目标蓝牙mac地址
    def get_ble_mac_address(self):
        asyncio.run(self.find_ble_devices())
        for dev in self.m_devices:
            if str(dev.name).find(self.m_device_name) != -1:
                self.m_device_mac_address = dev.address
                if DEBUG_PRINT_ON:
                    print("BCI_BLE device found - mac:", self.m_device_mac_address)
                return True
        if DEBUG_PRINT_ON:
            print("No BCI_BLE device found")
        return False

    def get_ble_mac_address_specefic(self, max_retries=10, retry_interval=1):
        retry_count = 0
        while retry_count < max_retries:
            try:
                asyncio.run(self.find_ble_devices())
                for dev in self.m_devices:
                    if str(dev.name).find(self.m_device_name) != -1:   
                        self.m_device_mac_address = dev.address
                        if DEBUG_PRINT_ON:
                            print(f"找到目标设备 {dev.name}，MAC地址: {self.m_device_mac_address}")
                        return True
                
                if DEBUG_PRINT_ON:
                    print(f"第{retry_count+1}次尝试未找到设备，等待{retry_interval}秒后重试...")
                retry_count += 1
                time.sleep(retry_interval)
                
            except Exception as e:
                if DEBUG_PRINT_ON:
                    print(f"扫描异常: {str(e)}，等待{retry_interval}秒后重试...")
                retry_count += 1
                time.sleep(retry_interval)
        
        if DEBUG_PRINT_ON:
            print(f"已达到最大重试次数{max_retries}，未找到指定设备，期望名称列表: {self.bci_ble_names}")
        return False

    # 接收数据
    async def start_notification(self):
        try:
            async with BleakClient(self.m_device_mac_address) as self.m_client:
                if DEBUG_PRINT_ON:
                    print("BCI_BLE device connected")
                if hasattr(self.m_client, '_acquire_mtu'):
                    await self.m_client._acquire_mtu()
                    if DEBUG_PRINT_ON:
                        print(f"当前 MTU: {self.m_client.mtu_size}")
                # WRITE_CH1 = "0000ffe3-0000-1000-8000-00805f9b34fb"
                self.m_client_serv = self.m_client.services

                # for service in self.m_client.services:
                #     print(f"\n[Service] {service.uuid}")
                #     for char in service.characteristics:
                #         props = ",".join(char.properties)
                #         print(f"  [Characteristic] {char.uuid} | Handle: {char.handle} | Props: [{props}]")
                if DEBUG_PRINT_ON:
                    print("BCI_BLE Services:")
                    for service in self.m_client_serv:
                        print("\t", service)
                        for char in service.characteristics:
                            print("\t\t", char)
                self.event = asyncio.Event()
                await self.m_client.start_notify(5, self.notification_handler)
                # await self.m_client.start_notify(42, self.notification_handler)
                await self.event.wait()  # 持续接收数据，直到进程终止
        except Exception as e:
            if DEBUG_PRINT_ON:
                print(f"连接异常: {str(e)}")
            # 添加重连逻辑
            await asyncio.sleep(1)
            await self.start_notification()
            # await self.m_client.stop_notify(42)

    # 接收数据回调函数
    async def notification_handler(self, sender, data):
        global g_data_counter, g_timer_begin, g_timer_end, raw_data
        if self.is_receiving:
            head_len = 3
            if self.channel_num == 8:
                data_length = 140
                single_frame = 24
                battery = data[136:138]
            # print(len(data))
            if LOG_ON:
                if DEBUG_PRINT_ON:
                    self.logger.debug('have received buffer')
                    self.logger.debug('len: %d', len(data))
                    self.logger.debug('data: %s', bytes(data).hex())
            if len(data) == data_length:
                raw_data = []
            raw_data.extend(data)
            if len(raw_data) >= data_length:
                # print(len(raw_data))
                data = raw_data[:data_length]
                # print(len(data))
                raw_data[:data_length] = []
                # print(len(data))
                # print(order)
                # print(int.from_bytes(order, byteorder="little", signed=False))
                data_eeg = data[head_len: head_len + single_frame * SAMPLES_PER_FRAME]
                data_trigger = data[head_len + single_frame * SAMPLES_PER_FRAME: head_len + single_frame * SAMPLES_PER_FRAME + TRIGGER_LENGTH]
                
                # 解析电量
                if self.battery_queue is not None and g_data_counter % 50 == 0:
                    try:
                        battery_bytes = data[136:138]
                        battery_level = int.from_bytes(battery_bytes, byteorder="big", signed=False)
                        # print("电量:",battery_level)
                        # 使用非阻塞方式放入队列，防止队列满时阻塞
                        if not self.battery_queue.full():
                            self.battery_queue.put(battery_level)
                    except Exception as e:
                        if LOG_ON:
                            self.logger.error(f"Error parsing battery: {e}")

                # Frame_header_A = data[0]
                # Frame_header_B = data[1]
                # order = data[2]
                # print(data_trigger)
                g_data_counter = g_data_counter + 1
                # battery = data[136:138]
                raw_data_one_frame = np.zeros([self.channel_num + 1, SAMPLES_PER_FRAME])
                for frame_idx in range(0, SAMPLES_PER_FRAME):
                    for ch_idx in range(0, self.channel_num):
                        raw_data_one_frame[ch_idx][frame_idx] = int.from_bytes(data_eeg[(3 * ch_idx + single_frame * frame_idx):
                                                                                        (3 * ch_idx + single_frame * frame_idx + 3)],
                                                                                        byteorder="big", signed=True)
                    # raw_data_one_frame[8][frame_idx] = int.from_bytes(data_trigger[frame_idx: frame_idx + 1], byteorder="big", signed=False)
                    raw_data_one_frame[self.channel_num][frame_idx] = int.from_bytes(data_trigger, byteorder="big", signed=False)
                    # raw_data_one_frame[9][frame_idx] = Frame_header_A
                    # raw_data_one_frame[10][frame_idx] = Frame_header_B
                    # raw_data_one_frame[11][frame_idx] = len(data)
                    # raw_data_one_frame[12][frame_idx] = len(data)
                    

                # 得到的单帧数据raw_data_one_frame，一帧内有SAMPLES_PER_FRAME个采样点
                # 得到的所有数据raw_data
                # print('have received data')
                for j in range(raw_data_one_frame.shape[1]):
                    self.outlet.push_sample(raw_data_one_frame[:,j],timestamp = time.time())
                    # sio.savemat("raw_data.mat", {"rawData": raw_data_one_frame[:,j]})
                # raw_data = np.concatenate((raw_data, raw_data_one_frame), axis=1)
                # t = 0
                if DEBUG_ON and (g_data_counter >= 50):
                    # print('have received data')
                    # print(f"当前 MTU: {self.m_client.mtu_size}")
                    try:
                        print(int.from_bytes(battery, byteorder="big", signed=False))
                    except:
                        pass
                    # print("140:",data[139])
                    # print("139:",data[138])
                    # print("138:",data[137])
                    # print("137:",data[136])
                    # print("136:",data[135])
                    # print("135:",data[134])
                    # print("134:",data[133])
                #     g_timer_begin = g_timer_end
                #     g_timer_end = time.perf_counter()
                #     # timestamps = [t / 256]
                #     print("receive data cost:", g_timer_end - g_timer_begin, "\tlen:", len(data))
                    g_data_counter = 0
        else:
            self.event.set()


    def read_config_CHlen(self):
        config = configparser.ConfigParser()
        config_name='external_modules/BHBconfig.ini'
        config.read(config_name, encoding='utf - 8')
        channel_names = eval(config['Channel']['channel_names'])
        return len(channel_names)

    def process_commands(self,queue,host,port):
        """处理来自socket的指令"""
        while not self.m_client:
            # print("111111")
            time.sleep(1)
            continue
        while not self.m_client.is_connected:
            # print("22222")
            time.sleep(1)
            continue
        queue.put("ble connected")
        command_data = bytearray([0x02, 0x02])
        self.run_async(self.send_control_command(command_data))
        command_data = bytearray([0x02, 0x01])
        self.run_async(self.send_control_command(command_data))
        # command_data = bytearray([0xFF, 0x02])  # 重置trigger
        # self.run_async(self.send_control_command(command_data))
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # 创建套接字
        server_socket.bind((host, port))     # 将地址（主机名、端口号）绑定到套接字上
        server_socket.listen(5)
        while True:
            try:
                client_socket, address = server_socket.accept()     # 被动接受TCP客户端连接，持续等待直到连接到达（阻塞等待）。
                if DEBUG_PRINT_ON:
                    print("连接来自: %s:%s" % address)  # 阻塞直到接收到一个指令
                while True:
                    command = client_socket.recv(1024)
                    command = command.decode(encoding='utf-8')
                    if DEBUG_PRINT_ON:
                        print(command)
                    if command.startswith("start"):
                        if DEBUG_PRINT_ON:
                            print("开始trigger")
                        self.word = command
                        # command_data = bytearray([0x02, 0x01])
                        # self.run_async(self.send_control_command(command_data))
                        command_data = bytearray([0xFF, 0x01])  # 设置trigger
                        self.run_async(self.send_control_command(command_data))
                    elif command == "end":
                        if DEBUG_PRINT_ON:
                            print("停止trigger")
                        command_data = bytearray([0xFF, 0x02])  # 重置trigger
                        self.run_async(self.send_control_command(command_data))
                        # self.is_receiving = False  # 停止接收数据
                    elif command == "del":
                        if DEBUG_PRINT_ON:
                            print("退出接收")
                        self.is_receiving = False
                        break
            except ConnectionResetError:
                if DEBUG_PRINT_ON:
                    print("客户端 %s:%s异常断开连接" % address)
                continue

    async def send_control_command(self, command_data):
        """异步发送控制指令到蓝牙设备的特征值41"""
        WRITE_CH1 = "0000ffe3-0000-1000-8000-00805f9b34fb"
        # print("82uu9")
        # char = self.m_client.get_characteristic(WRITE_CH1)
        if self.m_client and self.m_client.is_connected:
            if DEBUG_PRINT_ON:
                print(f"Sending control command char 40: {command_data}")
            await self.m_client.write_gatt_char(8, command_data)
            # await self.m_client.write_gatt_char(40, command_data)

    def run_async(self, coro):
        """在子线程中运行异步协程"""
        loop = asyncio.new_event_loop()  # 创建新的事件循环
        asyncio.set_event_loop(loop)  # 设置当前线程的事件循环
        loop.run_until_complete(coro)  # 运行协程

    def start_recv(self):
        asyncio.run(self.start_notification())

def breceive(queue:multiprocessing.Queue, host:str, port:int, device:str, log_file_path: str = 'ble_receiver.log', battery_queue=None):
    """
    BLE主接收函数
    Args:
        queue: 多进程队列，用于传递连接状态
        host: 指令服务监听地址
        port: 指令服务监听端口
        device: 设备标识符（用于自动发现串口）
        log_file_path: 日志文件保存路径 (默认为 'ble_receiver.log')
        battery_queue: 用于传递电量数据的队列
    Steps:
        1. 初始化BLE接收器
        2. 扫描并获取目标设备MAC地址
        3. 启动命令处理线程
        4. 开始异步数据接收
    """
    receiver = BleReceiver(device, log_file_path, battery_queue)
    if not receiver.get_ble_mac_address_specefic():  # 获取目标蓝牙mac地址
        if DEBUG_PRINT_ON:
            print("未找到目标蓝牙设备，程序已退出")
        exit()
    command_thread = threading.Thread(target=receiver.process_commands, args=(queue,host, port))
    command_thread.start()
    if LOG_ON:
        receiver.logger.info('命令处理线程已启动')
    # queue.put("ble connected")
    receiver.start_recv()  # 启动BLE接收任务
    with open('xw_web.json','w') as f:
        device_json = {'device': device}
        json_str = json.dumps(device_json)
        f.write(json_str)
    command_thread.join()


if __name__ == "__main__":
    queue = multiprocessing.Queue()
    default_log_path = os.path.join(os.path.dirname(__file__), 'ble_receiver.log')
    breceive(queue, "127.0.0.1", 8080, "MSM", default_log_path)