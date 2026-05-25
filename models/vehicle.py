"""
车辆模型
"""

import math
from enum import Enum

class VehicleStatus(Enum):
    """车辆状态枚举"""
    IDLE = "idle"              # 空闲
    MOVING = "moving"          # 移动中
    CHARGING = "charging"      # 充电中
    DELIVERING = "delivering"  # 配送中
    COOPERATIVE = "cooperative" # 协同配送中
    RETURNING = "returning"    # 返回仓库中

class Vehicle:
    """
    新能源物流车辆类
    """
    def __init__(self, vehicle_id, capacity, max_battery, current_battery=None, 
                 current_location=None, status=VehicleStatus.IDLE):
        """
        初始化车辆
        
        参数:
        - vehicle_id: 车辆ID
        - capacity: 最大载重(kg)
        - max_battery: 最大电量(km行驶距离)
        - current_battery: 当前电量(km)，默认为满电
        - current_location: 当前位置(节点ID)，默认为仓库
        - status: 车辆状态
        """
        self.id = vehicle_id
        self.capacity = capacity
        self.max_battery = max_battery
        self.current_battery = current_battery if current_battery is not None else max_battery
        self.current_location = current_location
        self.status = status
        
        # 任务相关属性
        self.current_task = None
        self.schedule = []  # 任务计划表
        self.current_path = []  # 当前行驶路径
        self.path_progress = 0  # 在当前路径上的进度
        
        # 充电相关属性
        self.charging_station = None
        self.charge_start_time = None
        
        # 统计信息
        self.total_distance = 0  # 总行驶距离
        self.total_tasks = 0  # 完成任务数
        self.total_charge_time = 0  # 总充电时间
        self.utilization_rate = 0  # 利用率
        
        # 电量消耗率(每公里消耗的电量比例)
        self.battery_consumption_rate = 0.1
    
    def copy(self):
        """创建车辆的深拷贝"""
        new_vehicle = Vehicle(
            vehicle_id=self.id,
            capacity=self.capacity,
            max_battery=self.max_battery,
            current_battery=self.current_battery,
            current_location=self.current_location,
            status=self.status
        )
        new_vehicle.current_task = self.current_task
        new_vehicle.schedule = self.schedule.copy()
        new_vehicle.current_path = self.current_path.copy()
        new_vehicle.path_progress = self.path_progress
        new_vehicle.charging_station = self.charging_station
        new_vehicle.charge_start_time = self.charge_start_time
        new_vehicle.total_distance = self.total_distance
        new_vehicle.total_tasks = self.total_tasks
        new_vehicle.total_charge_time = self.total_charge_time
        new_vehicle.utilization_rate = self.utilization_rate
        new_vehicle.battery_consumption_rate = self.battery_consumption_rate
        return new_vehicle
    
    def get_remaining_capacity(self):
        """获取剩余载重能力"""
        if self.current_task:
            return self.capacity - self.current_task.weight
        return self.capacity
    
    def get_remaining_battery(self):
        """获取剩余电量百分比"""
        return (self.current_battery / self.max_battery) * 100
    
    def is_battery_low(self, threshold=0.2):
        """
        检查电量是否低
        
        参数:
        - threshold: 低电量阈值，默认20%
        
        返回:
        - bool: 电量是否低于阈值
        """
        return self.get_remaining_battery() < threshold * 100
    
    def can_reach(self, distance):
        """
        检查是否有足够电量到达指定距离
        
        参数:
        - distance: 距离(km)
        
        返回:
        - bool: 是否有足够电量
        """
        return self.current_battery >= distance
    
    def calculate_battery_after_trip(self, distance):
        """
        计算行驶指定距离后的剩余电量
        
        参数:
        - distance: 距离(km)
        
        返回:
        - float: 剩余电量(km)
        """
        return max(0, self.current_battery - distance)
    
    def consume_battery(self, distance):
        """
        消耗电量
        
        参数:
        - distance: 行驶距离(km)
        """
        self.current_battery = max(0, self.current_battery - distance)
        self.total_distance += distance
    
    def charge_battery(self, amount):
        """
        充电
        
        参数:
        - amount: 充电量(km)
        """
        self.current_battery = min(self.max_battery, self.current_battery + amount)
    
    def start_charging(self, station):
        """
        开始充电
        
        参数:
        - station: 充电站对象
        """
        self.status = VehicleStatus.CHARGING
        self.charging_station = station
        self.charge_start_time = 0  # 这里应该是实际时间，简化处理
    
    def stop_charging(self):
        """停止充电"""
        self.status = VehicleStatus.IDLE
        self.charging_station = None
        self.charge_start_time = None
    
    def assign_task(self, task):
        """
        分配任务
        
        参数:
        - task: 任务对象
        """
        self.current_task = task
        self.status = VehicleStatus.MOVING if task else VehicleStatus.IDLE
    
    def complete_task(self):
        """完成当前任务"""
        if self.current_task:
            self.total_tasks += 1
            self.current_task = None
            self.status = VehicleStatus.IDLE
    
    def update_location(self, new_location):
        """
        更新车辆位置
        
        参数:
        - new_location: 新位置(节点ID)
        """
        self.current_location = new_location
    
    def set_path(self, path):
        """
        设置行驶路径
        
        参数:
        - path: 路径节点ID列表
        """
        self.current_path = path
        self.path_progress = 0
    
    def move_along_path(self, step=1):
        """
        沿路径移动
        
        参数:
        - step: 移动步数
        
        返回:
        - bool: 是否到达路径终点
        """
        if not self.current_path or self.path_progress >= len(self.current_path) - 1:
            return True
        
        self.path_progress += step
        if self.path_progress >= len(self.current_path) - 1:
            self.path_progress = len(self.current_path) - 1
            self.current_location = self.current_path[-1]
            return True
        
        self.current_location = self.current_path[self.path_progress]
        return False
    
    def to_dict(self):
        """
        转换为字典格式
        
        返回:
        - dict: 车辆信息字典
        """
        return {
            'id': self.id,
            'capacity': self.capacity,
            'max_battery': self.max_battery,
            'current_battery': self.current_battery,
            'current_location': self.current_location,
            'status': self.status.value,
            'total_distance': self.total_distance,
            'total_tasks': self.total_tasks,
            'remaining_battery_percent': self.get_remaining_battery()
        }

def create_default_fleet(depot_location, fleet_size=10):
    """
    创建默认车队
    
    参数:
    - depot_location: 仓库位置(节点ID)
    - fleet_size: 车队规模
    
    返回:
    - list: 车辆对象列表
    """
    fleet = []
    
    # 创建不同类型的车辆
    for i in range(fleet_size):
        if i < 3:  # 3辆大型车
            vehicle = Vehicle(
                vehicle_id=i+1,
                capacity=1500,  # 1.5吨
                max_battery=200,  # 200km
                current_location=depot_location
            )
        elif i < 7:  # 4辆中型车
            vehicle = Vehicle(
                vehicle_id=i+1,
                capacity=800,  # 0.8吨
                max_battery=150,  # 150km
                current_location=depot_location
            )
        else:  # 3辆小型车
            vehicle = Vehicle(
                vehicle_id=i+1,
                capacity=500,  # 0.5吨
                max_battery=100,  # 100km
                current_location=depot_location
            )
        fleet.append(vehicle)
    
    return fleet

if __name__ == "__main__":
    # 测试车辆类
    depot_node = 100  # 仓库节点ID
    
    # 创建一辆测试车辆
    test_vehicle = Vehicle(
        vehicle_id=1,
        capacity=1000,
        max_battery=200,
        current_location=depot_node
    )
    
    print("初始车辆状态:")
    print(f"ID: {test_vehicle.id}")
    print(f"载重: {test_vehicle.capacity}kg")
    print(f"电量: {test_vehicle.current_battery}/{test_vehicle.max_battery}km ({test_vehicle.get_remaining_battery():.1f}%)")
    print(f"位置: 节点{test_vehicle.current_location}")
    print(f"状态: {test_vehicle.status.value}")
    
    # 测试电量消耗
    distance = 50  # km
    test_vehicle.consume_battery(distance)
    print(f"\n行驶{distance}km后:")
    print(f"剩余电量: {test_vehicle.current_battery}km ({test_vehicle.get_remaining_battery():.1f}%)")
    print(f"总行驶距离: {test_vehicle.total_distance}km")
    
    # 测试充电
    charge_amount = 100  # km
    test_vehicle.charge_battery(charge_amount)
    print(f"\n充电{charge_amount}km后:")
    print(f"电量: {test_vehicle.current_battery}km ({test_vehicle.get_remaining_battery():.1f}%)")
    
    # 测试低电量警告
    test_vehicle.current_battery = 30  # 设置低电量
    print(f"\n设置电量为30km后:")
    print(f"电量低警告: {test_vehicle.is_battery_low()}")
    print(f"能否行驶50km: {test_vehicle.can_reach(50)}")
    print(f"能否行驶20km: {test_vehicle.can_reach(20)}")