"""
充电站模型
"""

from collections import deque

class ChargingStation:
    """
    充电站类
    """
    def __init__(self, station_id, node_id, location, capacity, charging_rate):
        """
        初始化充电站
        
        参数:
        - station_id: 充电站ID
        - node_id: 所在节点ID
        - location: 位置坐标(经纬度)
        - capacity: 充电桩数量
        - charging_rate: 充电速率(km电量/分钟)
        """
        self.id = station_id
        self.node_id = node_id
        self.location = location
        self.capacity = capacity
        self.charging_rate = charging_rate
        
        # 充电队列和占用状态
        self.queue = deque()  # 排队车辆队列
        self.occupied = []    # 当前充电中车辆列表
        
        # 统计信息
        self.total_vehicles = 0  # 总服务车辆数
        self.total_charge_time = 0  # 总充电时间
        self.total_charge_amount = 0  # 总充电量
        self.queue_waiting_time = 0  # 总排队等待时间
        
        # 历史记录
        self.usage_history = []  # 使用率历史记录
        self.queue_length_history = []  # 队列长度历史记录
    
    def copy(self):
        """创建充电站的深拷贝"""
        new_station = ChargingStation(
            station_id=self.id,
            node_id=self.node_id,
            location=self.location,
            capacity=self.capacity,
            charging_rate=self.charging_rate
        )
        new_station.queue = deque(self.queue)
        new_station.occupied = self.occupied.copy()
        new_station.total_vehicles = self.total_vehicles
        new_station.total_charge_time = self.total_charge_time
        new_station.total_charge_amount = self.total_charge_amount
        new_station.queue_waiting_time = self.queue_waiting_time
        new_station.usage_history = self.usage_history.copy()
        new_station.queue_length_history = self.queue_length_history.copy()
        return new_station
    
    def add_vehicle(self, vehicle, current_time):
        """
        添加车辆到充电站
        
        参数:
        - vehicle: 车辆对象
        - current_time: 当前时间(秒)
        
        返回:
        - bool: 是否立即开始充电
        """
        # 记录车辆到达时间
        vehicle.charge_start_time = current_time
        
        # 如果有空闲充电桩，立即开始充电
        if len(self.occupied) < self.capacity:
            self.occupied.append(vehicle)
            vehicle.status = "charging"
            vehicle.charging_station = self
            return True
        
        # 否则加入排队队列
        self.queue.append((vehicle, current_time))
        vehicle.status = "waiting"
        return False
    
    def remove_vehicle(self, vehicle):
        """
        从充电站移除车辆
        
        参数:
        - vehicle: 车辆对象
        
        返回:
        - bool: 是否成功移除
        """
        # 从充电中列表移除
        if vehicle in self.occupied:
            self.occupied.remove(vehicle)
            vehicle.status = "idle"
            vehicle.charging_station = None
            self.total_vehicles += 1
            
            # 处理队列中下一辆车
            self.process_queue()
            return True
        
        # 从排队队列移除
        for i, (v, _) in enumerate(self.queue):
            if v == vehicle:
                self.queue.remove((v, _))
                vehicle.status = "idle"
                vehicle.charging_station = None
                return True
        
        return False
    
    def process_queue(self):
        """处理充电队列，安排下一辆车充电"""
        if self.queue and len(self.occupied) < self.capacity:
            vehicle, arrival_time = self.queue.popleft()
            
            # 计算等待时间
            waiting_time = self.current_time - arrival_time if hasattr(self, 'current_time') else 0
            self.queue_waiting_time += waiting_time
            
            # 开始充电
            self.occupied.append(vehicle)
            vehicle.status = "charging"
            vehicle.charge_start_time = self.current_time if hasattr(self, 'current_time') else 0
    
    def update(self, time_delta):
        """
        更新充电站状态
        
        参数:
        - time_delta: 时间增量(秒)
        """
        # 更新当前时间
        if not hasattr(self, 'current_time'):
            self.current_time = 0
        self.current_time += time_delta
        
        # 为充电中的车辆充电
        for vehicle in self.occupied:
            # 计算充电量
            charge_amount = (self.charging_rate * time_delta) / 60  # 转换为km电量
            
            # 充电
            old_battery = vehicle.current_battery
            vehicle.charge_battery(charge_amount)
            actual_charge = vehicle.current_battery - old_battery
            
            # 更新统计信息
            self.total_charge_amount += actual_charge
            self.total_charge_time += time_delta
        
        # 记录历史数据
        self.record_history()
    
    def record_history(self):
        """记录充电站历史数据"""
        # 每5分钟记录一次
        if self.current_time % 300 == 0:
            usage_rate = len(self.occupied) / self.capacity
            self.usage_history.append((self.current_time, usage_rate))
            
            queue_length = len(self.queue)
            self.queue_length_history.append((self.current_time, queue_length))
    
    def get_available_spots(self):
        """获取可用充电桩数量"""
        return self.capacity - len(self.occupied)
    
    def get_queue_length(self):
        """获取排队车辆数量"""
        return len(self.queue)
    
    def get_utilization_rate(self):
        """获取充电站利用率"""
        if self.total_vehicles == 0:
            return 0
        
        return len(self.occupied) / self.capacity
    
    def get_average_waiting_time(self):
        """获取平均等待时间"""
        if self.total_vehicles == 0:
            return 0
        
        return self.queue_waiting_time / self.total_vehicles
    
    def to_dict(self):
        """
        转换为字典格式
        
        返回:
        - dict: 充电站信息字典
        """
        return {
            'id': self.id,
            'node_id': self.node_id,
            'location': self.location,
            'capacity': self.capacity,
            'charging_rate': self.charging_rate,
            'occupied': len(self.occupied),
            'queue_length': len(self.queue),
            'available_spots': self.get_available_spots(),
            'utilization_rate': self.get_utilization_rate()
        }

def create_charging_stations_from_data():
    """
    从数据创建充电站列表
    
    返回:
    - list: 充电站对象列表
    """
    from data.guangzhou_map import CHARGING_STATIONS, get_node_coordinates, get_node_name
    
    stations = []
    for sid, node_id, capacity, charging_rate in CHARGING_STATIONS:
        location = get_node_coordinates(node_id)
        station = ChargingStation(
            station_id=sid,
            node_id=node_id,
            location=location,
            capacity=capacity,
            charging_rate=charging_rate
        )
        stations.append(station)
    
    return stations

if __name__ == "__main__":
    # 测试充电站类
    from data.guangzhou_map import create_guangzhou_graph, get_node_coordinates
    from models.vehicle import Vehicle, VehicleStatus
    
    # 创建地图
    G = create_guangzhou_graph()
    
    # 创建测试充电站
    station = ChargingStation(
        station_id=1,
        node_id=1,
        location=get_node_coordinates(1),
        capacity=5,
        charging_rate=2.0  # 2km/分钟
    )
    
    print("初始充电站状态:")
    print(f"ID: {station.id}")
    print(f"位置: 节点{station.node_id}")
    print(f"充电桩数量: {station.capacity}")
    print(f"充电速率: {station.charging_rate} km/分钟")
    print(f"可用充电桩: {station.get_available_spots()}")
    print(f"排队车辆: {station.get_queue_length()}")
    
    # 创建测试车辆
    vehicles = []
    for i in range(8):  # 创建8辆车，超过充电站容量
        vehicle = Vehicle(
            vehicle_id=i+1,
            capacity=1000,
            max_battery=200,
            current_battery=50,  # 低电量
            current_location=1
        )
        vehicles.append(vehicle)
    
    # 测试车辆充电
    print("\n车辆充电测试:")
    for i, vehicle in enumerate(vehicles):
        immediate_charge = station.add_vehicle(vehicle, i * 60)  # 每辆车间隔1分钟到达
        status = "立即充电" if immediate_charge else "排队等待"
        print(f"车辆{vehicle.id}到达: {status}, 剩余电量: {vehicle.current_battery}km")
    
    print(f"\n充电站状态更新:")
    print(f"充电中车辆: {len(station.occupied)}")
    print(f"排队车辆: {len(station.queue)}")
    print(f"可用充电桩: {station.get_available_spots()}")
    print(f"利用率: {station.get_utilization_rate():.1%}")
    
    # 测试充电过程
    print("\n充电过程模拟(30分钟):")
    station.update(30 * 60)  # 30分钟
    
    for vehicle in station.occupied:
        print(f"车辆{vehicle.id}: 电量从50km充至 {vehicle.current_battery:.1f}km")
    
    # 测试车辆离开
    print("\n测试车辆离开:")
    leaving_vehicle = station.occupied[0]
    station.remove_vehicle(leaving_vehicle)
    print(f"车辆{leaving_vehicle.id}离开后:")
    print(f"充电中车辆: {len(station.occupied)}")
    print(f"排队车辆: {len(station.queue)}")
    print(f"可用充电桩: {station.get_available_spots()}")