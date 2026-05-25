"""
模拟器模块
整合所有组件，模拟新能源物流车队调度过程
"""

import time
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from data.guangzhou_map import (
    create_guangzhou_graph, get_depot_location, get_node_name,
    get_node_coordinates, get_all_charging_stations
)
from models.vehicle import Vehicle, VehicleStatus, create_default_fleet
from models.task import Task, TaskStatus, TaskGenerator
from models.charging_station import ChargingStation, create_charging_stations_from_data
from algorithms.path_planning import (
    shortest_path, calculate_path_distance, has_enough_battery,
    find_optimal_charging_station
)
from algorithms.scheduling_strategy import (
    create_strategy, cooperative_task_allocation, charging_strategy
)

class Simulator:
    """
    新能源物流车队调度模拟器
    """
    def __init__(self, fleet_size=10, simulation_time=3600*8, 
                 task_rate=0.01, strategy_name="balanced", 
                 enable_cooperation=True, enable_charging=True):
        """
        初始化模拟器
        
        参数:
        - fleet_size: 车队规模
        - simulation_time: 模拟时间(秒)，默认8小时
        - task_rate: 每秒生成任务的概率
        - strategy_name: 调度策略名称
        - enable_cooperation: 是否启用多车协同
        - enable_charging: 是否启用充电管理
        """
        # 初始化地图
        self.graph = create_guangzhou_graph()
        
        # 获取仓库位置
        self.depot_id, self.depot_lat, self.depot_lon, self.depot_name = get_depot_location()
        
        # 初始化车队
        self.fleet = create_default_fleet(self.depot_id, fleet_size)
        
        # 初始化充电站
        self.charging_stations = create_charging_stations_from_data()
        
        # 初始化任务生成器
        self.task_generator = TaskGenerator(
            self.graph, 
            min_weight=10, 
            max_weight=1000,
            task_rate=task_rate,
            deadline_rate=0.7
        )
        
        # 初始化调度策略
        self.strategy = create_strategy(strategy_name)
        
        # 模拟参数
        self.simulation_time = simulation_time
        self.current_time = 0
        self.time_step = 10  # 时间步长(秒)
        
        # 任务列表
        self.tasks = []
        self.completed_tasks = []
        self.failed_tasks = []
        
        # 统计信息
        self.total_score = 0
        self.total_tasks = 0
        self.completed_task_count = 0
        self.failed_task_count = 0
        self.average_task_time = 0
        self.average_task_distance = 0
        self.vehicle_utilization = 0
        self.charging_station_utilization = 0
        
        # 历史记录
        self.history = {
            "time": [],
            "pending_tasks": [],
            "completed_tasks": [],
            "failed_tasks": [],
            "total_score": [],
            "vehicle_utilization": [],
            "charging_utilization": []
        }
        
        # 配置选项
        self.enable_cooperation = enable_cooperation
        self.enable_charging = enable_charging
        
        # 可视化数据
        self.visualization_data = {
            "vehicles": [],
            "tasks": [],
            "charging_stations": []
        }
        
        # 车辆历史路径数据
        self.vehicle_history = []
    
    def reset(self):
        """重置模拟器"""
        # 重新初始化车队
        self.fleet = create_default_fleet(self.depot_id, len(self.fleet))
        
        # 重置任务列表
        self.tasks = []
        self.completed_tasks = []
        self.failed_tasks = []
        
        # 重置统计信息
        self.current_time = 0
        self.total_score = 0
        self.total_tasks = 0
        self.completed_task_count = 0
        self.failed_task_count = 0
        
        # 重置历史记录
        self.history = {
            "time": [],
            "pending_tasks": [],
            "completed_tasks": [],
            "failed_tasks": [],
            "total_score": [],
            "vehicle_utilization": [],
            "charging_utilization": []
        }
        
        # 重置车辆历史路径数据
        self.vehicle_history = []
    
    def generate_tasks(self):
        """生成新任务"""
        new_tasks = self.task_generator.generate_tasks(self.current_time)
        self.tasks.extend(new_tasks)
        self.total_tasks += len(new_tasks)
        
        # 每小时有10%概率生成一个大型任务
        if self.current_time % 3600 == 0 and random.random() < 0.1:
            large_task = self.task_generator.generate_large_task(self.current_time)
            self.tasks.append(large_task)
            self.total_tasks += 1
    
    def update_vehicle_states(self):
        """更新车辆状态"""
        for vehicle in self.fleet:
            if vehicle.status == VehicleStatus.MOVING and vehicle.current_path:
                # 车辆沿路径移动
                reached_end = vehicle.move_along_path(step=1)
                
                if reached_end:
                    # 到达目的地
                    if vehicle.current_task:
                        # 完成任务
                        task = vehicle.current_task
                        task.complete(self.current_time)
                        self.completed_tasks.append(task)
                        self.tasks.remove(task)
                        self.completed_task_count += 1
                        
                        # 更新统计信息
                        self.total_score += task.score
                        self.average_task_time = (
                            (self.average_task_time * (self.completed_task_count - 1) + 
                             (task.completion_time - task.start_time)) / 
                            self.completed_task_count
                        )
                        self.average_task_distance = (
                            (self.average_task_distance * (self.completed_task_count - 1) + 
                             task.total_distance) / 
                            self.completed_task_count
                        )
                        
                        # 重置车辆状态
                        vehicle.current_task = None
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.current_path = []
                    else:
                        # 无任务，设为空闲
                        vehicle.status = VehicleStatus.IDLE
                        vehicle.current_path = []
            
            elif vehicle.status == VehicleStatus.CHARGING:
                # 充电中，更新电量
                if vehicle.charging_station:
                    # 计算充电量
                    charge_amount = (vehicle.charging_station.charging_rate * self.time_step) / 60
                    vehicle.charge_battery(charge_amount)
                    
                    # 检查是否充满
                    if vehicle.current_battery >= vehicle.max_battery * 0.95:
                        # 充电完成
                        vehicle.charging_station.remove_vehicle(vehicle)
                        vehicle.status = VehicleStatus.IDLE
    
    def update_charging_stations(self):
        """更新充电站状态"""
        for station in self.charging_stations:
            station.update(self.time_step)
    
    def check_task_deadlines(self):
        """检查任务截止时间"""
        for task in self.tasks[:]:
            if task.deadline and self.current_time > task.deadline:
                # 任务超时失败
                task.fail(self.current_time)
                self.failed_tasks.append(task)
                self.tasks.remove(task)
                self.failed_task_count += 1
                
                # 更新统计信息
                self.total_score += task.score  # 失败任务的分数为负数
    
    def allocate_tasks(self):
        """分配任务"""
        # 首先处理协同任务
        if self.enable_cooperation:
            cooperation_allocations = cooperative_task_allocation(
                self.fleet, self.tasks, self.graph, self.charging_stations
            )
            
            # 为协同任务规划路径
            for task, vehicles in cooperation_allocations.items():
                for vehicle in vehicles:
                    # 规划路径
                    path = shortest_path(self.graph, vehicle.current_location, task.location)
                    if path:
                        vehicle.current_path = path
                        vehicle.status = VehicleStatus.MOVING
                        # 预留部分电量返回
                        required_battery = calculate_path_distance(self.graph, path) * 1.2
                        if not vehicle.can_reach(required_battery):
                            # 电量不足，需要充电
                            station, _ = find_optimal_charging_station(
                                vehicle, self.graph, self.charging_stations, task.location
                            )
                            if station:
                                # 先去充电
                                charge_path = shortest_path(self.graph, vehicle.current_location, station.node_id)
                                if charge_path:
                                    vehicle.current_path = charge_path
                                    vehicle.status = VehicleStatus.MOVING
                                    vehicle.charging_station = station
                                    station.add_vehicle(vehicle, self.current_time)
        
        # 使用选定策略分配常规任务
        pending_tasks = [t for t in self.tasks if t.status == TaskStatus.PENDING]
        idle_vehicles = [v for v in self.fleet if v.status == VehicleStatus.IDLE]
        
        for vehicle in idle_vehicles:
            task = self.strategy.select_task(vehicle, pending_tasks, self.graph, self.charging_stations)
            if task:
                # 分配任务
                task.assign_to_vehicle(vehicle)
                vehicle.assign_task(task)
                
                # 规划路径
                path = shortest_path(self.graph, vehicle.current_location, task.location)
                if path:
                    vehicle.current_path = path
                    vehicle.status = VehicleStatus.MOVING
                    
                    # 计算路径距离
                    distance = calculate_path_distance(self.graph, path)
                    task.total_distance = distance
                    
                    # 消耗电量
                    vehicle.consume_battery(distance)
                    
                    # 从待分配任务列表中移除
                    pending_tasks.remove(task)
    
    def manage_charging(self):
        """管理车辆充电"""
        if not self.enable_charging:
            return
        
        # 获取需要充电的车辆和充电站分配
        charging_allocations = charging_strategy(
            self.fleet, self.charging_stations, self.graph, self.current_time
        )
        
        # 执行充电分配
        for vehicle, station in charging_allocations.items():
            # 规划去充电站的路径
            path = shortest_path(self.graph, vehicle.current_location, station.node_id)
            if path:
                vehicle.current_path = path
                vehicle.status = VehicleStatus.MOVING
                vehicle.charging_station = station
                
                # 消耗电量
                distance = calculate_path_distance(self.graph, path)
                vehicle.consume_battery(distance)
    
    def update_statistics(self):
        """更新统计信息"""
        # 计算车辆利用率
        active_vehicles = sum(1 for v in self.fleet if v.status != VehicleStatus.IDLE)
        self.vehicle_utilization = active_vehicles / len(self.fleet)
        
        # 计算充电站利用率
        total_capacity = sum(s.capacity for s in self.charging_stations)
        total_occupied = sum(len(s.occupied) for s in self.charging_stations)
        self.charging_station_utilization = total_occupied / total_capacity if total_capacity > 0 else 0
    
    def record_history(self):
        """记录历史数据"""
        # 每60秒记录一次
        if self.current_time % 60 == 0:
            self.history["time"].append(self.current_time)
            self.history["pending_tasks"].append(len(self.tasks))
            self.history["completed_tasks"].append(len(self.completed_tasks))
            self.history["failed_tasks"].append(len(self.failed_tasks))
            self.history["total_score"].append(self.total_score)
            self.history["vehicle_utilization"].append(self.vehicle_utilization)
            self.history["charging_utilization"].append(self.charging_station_utilization)
    
    def update_visualization_data(self):
        """更新可视化数据"""
        # 每10秒更新一次可视化数据
        if self.current_time % 10 == 0:
            # 车辆数据
            vehicle_data = []
            for vehicle in self.fleet:
                if vehicle.current_location:
                    lat, lon = get_node_coordinates(vehicle.current_location)
                    vehicle_data.append({
                        "id": vehicle.id,
                        "location": (lat, lon),
                        "status": vehicle.status.value,
                        "battery": vehicle.current_battery,
                        "max_battery": vehicle.max_battery,
                        "current_task": vehicle.current_task.id if vehicle.current_task else None,
                        "path": vehicle.current_path
                    })
                    
                    # 记录车辆历史路径数据
                    if vehicle.current_path and len(vehicle.current_path) > 1:
                        self.vehicle_history.append({
                            "id": vehicle.id,
                            "path": vehicle.current_path,
                            "status": vehicle.status.value,
                            "timestamp": self.current_time
                        })
            
            # 任务数据
            task_data = []
            for task in self.tasks:
                if task.location:
                    lat, lon = get_node_coordinates(task.location)
                    task_data.append({
                        "id": task.id,
                        "location": (lat, lon),
                        "weight": task.weight,
                        "status": task.status.value,
                        "deadline": task.deadline,
                        "assigned_vehicles": [v.id for v in task.assigned_vehicles]
                    })
            
            # 充电站数据
            station_data = []
            for station in self.charging_stations:
                if station.node_id:
                    lat, lon = get_node_coordinates(station.node_id)
                    station_data.append({
                        "id": station.id,
                        "location": (lat, lon),
                        "capacity": station.capacity,
                        "occupied": len(station.occupied),
                        "queue": len(station.queue)
                    })
            
            self.visualization_data = {
                "vehicles": vehicle_data,
                "tasks": task_data,
                "charging_stations": station_data,
                "current_time": self.current_time
            }
    
    def run(self, verbose=True):
        """
        运行模拟
        
        参数:
        - verbose: 是否打印详细信息
        
        返回:
        - dict: 模拟结果统计
        """
        start_time = time.time()
        
        print(f"开始模拟...")
        print(f"模拟时间: {self.simulation_time/3600:.1f}小时")
        print(f"车队规模: {len(self.fleet)}辆")
        print(f"调度策略: {self.strategy.name}")
        print(f"协同配送: {'启用' if self.enable_cooperation else '禁用'}")
        print(f"充电管理: {'启用' if self.enable_charging else '禁用'}")
        print("-" * 50)
        
        # 模拟主循环
        while self.current_time < self.simulation_time:
            # 生成新任务
            self.generate_tasks()
            
            # 更新车辆状态
            self.update_vehicle_states()
            
            # 更新充电站状态
            self.update_charging_stations()
            
            # 检查任务截止时间
            self.check_task_deadlines()
            
            # 分配任务
            self.allocate_tasks()
            
            # 管理充电
            self.manage_charging()
            
            # 更新统计信息
            self.update_statistics()
            
            # 记录历史数据
            self.record_history()
            
            # 更新可视化数据
            self.update_visualization_data()
            
            # 打印进度
            if verbose and self.current_time % 3600 == 0:
                hours = self.current_time // 3600
                print(f"时间: {hours}小时 | "
                      f"待处理任务: {len(self.tasks)} | "
                      f"已完成任务: {len(self.completed_tasks)} | "
                      f"失败任务: {len(self.failed_tasks)} | "
                      f"总分: {self.total_score:.1f}")
            
            # 推进时间
            self.current_time += self.time_step
        
        # 计算最终统计
        self.update_statistics()
        
        # 生成结果报告
        results = self.generate_results()
        
        # 打印总结
        if verbose:
            print("-" * 50)
            print("模拟完成!")
            print(f"总耗时: {time.time() - start_time:.2f}秒")
            print(f"总任务数: {self.total_tasks}")
            print(f"完成任务: {self.completed_task_count} ({self.completed_task_count/self.total_tasks*100:.1f}%)")
            print(f"失败任务: {self.failed_task_count} ({self.failed_task_count/self.total_tasks*100:.1f}%)")
            print(f"总评分: {self.total_score:.1f}")
            print(f"平均任务时间: {self.average_task_time/60:.1f}分钟")
            print(f"平均任务距离: {self.average_task_distance/1000:.1f}公里")
            print(f"车辆平均利用率: {self.vehicle_utilization*100:.1f}%")
            print(f"充电站平均利用率: {self.charging_station_utilization*100:.1f}%")
        
        return results
    
    def generate_results(self):
        """生成模拟结果报告"""
        # 计算任务完成率
        completion_rate = (self.completed_task_count / self.total_tasks * 100 
                          if self.total_tasks > 0 else 0)
        
        # 计算平均任务分数
        avg_task_score = (sum(t.score for t in self.completed_tasks) / self.completed_task_count 
                         if self.completed_task_count > 0 else 0)
        
        # 计算车辆统计
        total_distance = sum(v.total_distance for v in self.fleet)
        avg_vehicle_distance = total_distance / len(self.fleet)
        avg_vehicle_tasks = sum(v.total_tasks for v in self.fleet) / len(self.fleet)
        
        # 计算充电站统计
        total_charging_time = sum(s.total_charge_time for s in self.charging_stations)
        total_charge_amount = sum(s.total_charge_amount for s in self.charging_stations)
        avg_waiting_time = sum(s.get_average_waiting_time() for s in self.charging_stations) / len(self.charging_stations)
        
        results = {
            "simulation_parameters": {
                "simulation_time": self.simulation_time,
                "fleet_size": len(self.fleet),
                "task_rate": self.task_generator.task_rate,
                "strategy": self.strategy.name,
                "enable_cooperation": self.enable_cooperation,
                "enable_charging": self.enable_charging
            },
            "task_statistics": {
                "total_tasks": self.total_tasks,
                "completed_tasks": self.completed_task_count,
                "failed_tasks": self.failed_task_count,
                "completion_rate": completion_rate,
                "total_score": self.total_score,
                "average_task_score": avg_task_score,
                "average_task_time": self.average_task_time,
                "average_task_distance": self.average_task_distance
            },
            "vehicle_statistics": {
                "total_distance": total_distance,
                "average_vehicle_distance": avg_vehicle_distance,
                "average_vehicle_tasks": avg_vehicle_tasks,
                "average_utilization": self.vehicle_utilization
            },
            "charging_statistics": {
                "total_charging_time": total_charging_time,
                "total_charge_amount": total_charge_amount,
                "average_waiting_time": avg_waiting_time,
                "average_utilization": self.charging_station_utilization
            },
            "history": self.history,
            "visualization_data": self.visualization_data
        }
        
        return results
    
    def save_results(self, filename):
        """保存模拟结果到文件"""
        import json
        
        results = self.generate_results()
        
        # 转换为JSON可序列化格式
        def convert_numpy(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            return obj
        
        # 递归转换
        def recursive_convert(obj):
            if isinstance(obj, dict):
                return {key: recursive_convert(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [recursive_convert(item) for item in obj]
            else:
                return convert_numpy(obj)
        
        serializable_results = recursive_convert(results)
        
        # 保存到文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, ensure_ascii=False, indent=2)
        
        print(f"结果已保存到 {filename}")
    
    def compare_strategies(self, strategies=["nearest", "max_weight", "urgency", "balanced"], 
                          runs_per_strategy=3):
        """
        比较不同调度策略的性能
        
        参数:
        - strategies: 要比较的策略列表
        - runs_per_strategy: 每个策略运行的次数
        
        返回:
        - DataFrame: 比较结果
        """
        import pandas as pd
        
        results = []
        
        for strategy_name in strategies:
            print(f"\n测试策略: {strategy_name}")
            
            for run in range(runs_per_strategy):
                print(f"  运行 {run+1}/{runs_per_strategy}")
                
                # 创建新的模拟器实例
                sim = Simulator(
                    fleet_size=len(self.fleet),
                    simulation_time=self.simulation_time,
                    task_rate=self.task_generator.task_rate,
                    strategy_name=strategy_name,
                    enable_cooperation=self.enable_cooperation,
                    enable_charging=self.enable_charging
                )
                
                # 运行模拟
                result = sim.run(verbose=False)
                
                # 记录结果
                results.append({
                    "strategy": strategy_name,
                    "run": run + 1,
                    "completion_rate": result["task_statistics"]["completion_rate"],
                    "total_score": result["task_statistics"]["total_score"],
                    "average_task_score": result["task_statistics"]["average_task_score"],
                    "average_task_time": result["task_statistics"]["average_task_time"] / 60,  # 转换为分钟
                    "average_task_distance": result["task_statistics"]["average_task_distance"] / 1000,  # 转换为公里
                    "vehicle_utilization": result["vehicle_statistics"]["average_utilization"] * 100,
                    "charging_utilization": result["charging_statistics"]["average_utilization"] * 100
                })
        
        # 转换为DataFrame
        df = pd.DataFrame(results)
        
        # 计算平均值和标准差
        summary = df.groupby("strategy").agg({
            "completion_rate": ["mean", "std"],
            "total_score": ["mean", "std"],
            "average_task_score": ["mean", "std"],
            "average_task_time": ["mean", "std"],
            "average_task_distance": ["mean", "std"],
            "vehicle_utilization": ["mean", "std"],
            "charging_utilization": ["mean", "std"]
        }).round(2)
        
        print("\n策略比较结果:")
        print(summary)
        
        return df, summary

if __name__ == "__main__":
    # 测试模拟器
    simulator = Simulator(
        fleet_size=10,
        simulation_time=3600*2,  # 2小时
        task_rate=0.02,
        strategy_name="balanced",
        enable_cooperation=True,
        enable_charging=True
    )
    
    # 运行模拟
    results = simulator.run()
    
    # 保存结果
    simulator.save_results("simulation_results.json")
    
    # 比较不同策略
    df, summary = simulator.compare_strategies()
    
    # 保存比较结果
    df.to_csv("strategy_comparison.csv", index=False)
    summary.to_csv("strategy_summary.csv")