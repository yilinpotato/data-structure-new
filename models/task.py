"""
任务模型
"""

from enum import Enum
import random
from datetime import datetime, timedelta

class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 待分配
    ASSIGNED = "assigned"    # 已分配
    IN_PROGRESS = "in_progress"  # 进行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    COOPERATIVE = "cooperative"  # 协同配送中

class Task:
    """
    配送任务类
    """
    def __init__(self, task_id, location, weight, start_time, deadline=None):
        """
        初始化任务
        
        参数:
        - task_id: 任务ID
        - location: 任务地点(节点ID)
        - weight: 货物重量(kg)
        - start_time: 任务生成时间(秒)
        - deadline: 截止时间(秒)，默认None表示无截止时间
        """
        self.id = task_id
        self.location = location
        self.weight = weight
        self.start_time = start_time
        self.deadline = deadline
        
        # 状态相关属性
        self.status = TaskStatus.PENDING
        self.assigned_vehicles = []  # 分配的车辆列表(支持多车协同)
        
        # 完成相关属性
        self.completion_time = None
        self.total_distance = 0  # 完成任务行驶总距离
        self.waiting_time = 0  # 等待分配的时间
        
        # 评分相关属性
        self.score = 0
        self.score_details = {}
    
    def copy(self):
        """创建任务的深拷贝"""
        new_task = Task(
            task_id=self.id,
            location=self.location,
            weight=self.weight,
            start_time=self.start_time,
            deadline=self.deadline
        )
        new_task.status = self.status
        new_task.assigned_vehicles = self.assigned_vehicles.copy()
        new_task.completion_time = self.completion_time
        new_task.total_distance = self.total_distance
        new_task.waiting_time = self.waiting_time
        new_task.score = self.score
        new_task.score_details = self.score_details.copy()
        return new_task
    
    def assign_to_vehicle(self, vehicle):
        """
        将任务分配给车辆
        
        参数:
        - vehicle: 车辆对象
        """
        if vehicle not in self.assigned_vehicles:
            self.assigned_vehicles.append(vehicle)
        
        # 如果是单车辆分配，直接设置为已分配状态
        if len(self.assigned_vehicles) == 1:
            self.status = TaskStatus.ASSIGNED
        # 如果是多车辆协同，设置为协同状态
        else:
            self.status = TaskStatus.COOPERATIVE
    
    def remove_vehicle(self, vehicle):
        """
        从任务中移除车辆
        
        参数:
        - vehicle: 车辆对象
        """
        if vehicle in self.assigned_vehicles:
            self.assigned_vehicles.remove(vehicle)
        
        # 更新任务状态
        if not self.assigned_vehicles:
            self.status = TaskStatus.PENDING
        elif len(self.assigned_vehicles) == 1:
            self.status = TaskStatus.ASSIGNED
        else:
            self.status = TaskStatus.COOPERATIVE
    
    def start(self):
        """开始执行任务"""
        if self.status in [TaskStatus.ASSIGNED, TaskStatus.COOPERATIVE]:
            self.status = TaskStatus.IN_PROGRESS
    
    def complete(self, completion_time):
        """
        完成任务
        
        参数:
        - completion_time: 完成时间(秒)
        """
        self.status = TaskStatus.COMPLETED
        self.completion_time = completion_time
        
        # 计算等待时间
        if self.assigned_vehicles:
            # 假设任务在分配后立即开始
            assign_time = self.start_time + self.waiting_time
            self.waiting_time = assign_time - self.start_time
        
        # 计算任务评分
        self.calculate_score()
    
    def fail(self, fail_time):
        """
        任务失败
        
        参数:
        - fail_time: 失败时间(秒)
        """
        self.status = TaskStatus.FAILED
        self.completion_time = fail_time
        
        # 计算失败扣分
        self.calculate_failure_score()
    
    def calculate_score(self):
        """计算任务完成后的评分"""
        if self.status != TaskStatus.COMPLETED:
            return 0
        
        base_score = 100  # 基础分数
        score_details = {}
        
        # 1. 时间奖励(越早完成分数越高)
        if self.deadline:
            time_available = self.deadline - self.start_time
            time_used = self.completion_time - self.start_time
            time_ratio = max(0, (time_available - time_used) / time_available)
            time_bonus = 50 * time_ratio
            score_details['time_bonus'] = time_bonus
        else:
            # 无截止时间，根据完成速度给予奖励
            completion_speed = min(1, 3600 / (self.completion_time - self.start_time + 1))  # 1小时内完成满分
            time_bonus = 50 * completion_speed
            score_details['time_bonus'] = time_bonus
        
        # 2. 距离惩罚(路径越短扣分越少)
        distance_penalty = min(50, self.total_distance / 1000)  # 每公里扣0.05分，最多扣50分
        score_details['distance_penalty'] = -distance_penalty
        
        # 3. 货物重量奖励(货物越重奖励越高)
        weight_bonus = min(30, self.weight / 100)  # 每100kg奖励1分，最多30分
        score_details['weight_bonus'] = weight_bonus
        
        # 4. 等待时间惩罚(等待时间越长扣分越多)
        waiting_penalty = min(20, self.waiting_time / 600)  # 每10分钟扣1分，最多扣20分
        score_details['waiting_penalty'] = -waiting_penalty
        
        # 计算总分
        total_score = base_score + sum(score_details.values())
        self.score = max(0, total_score)
        self.score_details = score_details
        
        return self.score
    
    def calculate_failure_score(self):
        """计算任务失败的扣分"""
        if self.status != TaskStatus.FAILED:
            return 0
        
        # 基础扣分
        base_penalty = 100
        
        # 根据失败时间计算额外扣分
        if self.deadline:
            # 如果在截止时间前失败，扣分较少
            if self.completion_time < self.deadline:
                time_ratio = (self.deadline - self.completion_time) / (self.deadline - self.start_time)
                time_factor = 0.5 + 0.5 * time_ratio  # 0.5-1.0倍
            else:
                # 超时失败，扣分更多
                overtime = self.completion_time - self.deadline
                time_factor = 1.0 + min(1.0, overtime / 3600)  # 1.0-2.0倍
        else:
            # 无截止时间，按任务持续时间计算
            task_duration = self.completion_time - self.start_time
            time_factor = min(2.0, 0.5 + task_duration / 3600)  # 0.5-2.0倍
        
        # 货物重量因子(越重的货物失败影响越大)
        weight_factor = min(2.0, 1.0 + self.weight / 1000)  # 1.0-2.0倍
        
        # 计算总扣分
        total_penalty = base_penalty * time_factor * weight_factor
        self.score = -total_penalty
        self.score_details = {
            'base_penalty': -base_penalty,
            'time_factor': time_factor,
            'weight_factor': weight_factor,
            'total_penalty': -total_penalty
        }
        
        return self.score
    
    def get_remaining_time(self, current_time):
        """
        获取剩余时间
        
        参数:
        - current_time: 当前时间(秒)
        
        返回:
        - float: 剩余时间(秒)，None表示无截止时间
        """
        if not self.deadline:
            return None
        
        return max(0, self.deadline - current_time)
    
    def is_urgent(self, current_time, urgent_threshold=3600):
        """
        检查任务是否紧急
        
        参数:
        - current_time: 当前时间(秒)
        - urgent_threshold: 紧急阈值(秒)，默认1小时
        
        返回:
        - bool: 是否紧急
        """
        remaining_time = self.get_remaining_time(current_time)
        if remaining_time is None:
            return False
        
        return remaining_time < urgent_threshold
    
    def to_dict(self):
        """
        转换为字典格式
        
        返回:
        - dict: 任务信息字典
        """
        return {
            'id': self.id,
            'location': self.location,
            'weight': self.weight,
            'start_time': self.start_time,
            'deadline': self.deadline,
            'status': self.status.value,
            'assigned_vehicles': [v.id for v in self.assigned_vehicles],
            'completion_time': self.completion_time,
            'score': self.score
        }

class TaskGenerator:
    """
    任务生成器类
    """
    def __init__(self, graph, min_weight=10, max_weight=1000, 
                 task_rate=0.1, deadline_rate=0.7):
        """
        初始化任务生成器
        
        参数:
        - graph: 道路网络图
        - min_weight: 最小货物重量(kg)
        - max_weight: 最大货物重量(kg)
        - task_rate: 每秒生成任务的概率
        - deadline_rate: 有截止时间的任务比例
        """
        self.graph = graph
        self.min_weight = min_weight
        self.max_weight = max_weight
        self.task_rate = task_rate
        self.deadline_rate = deadline_rate
        self.task_id_counter = 0
        
        # 排除仓库节点的所有其他节点
        self.delivery_nodes = [n for n in graph.nodes() if n != 100]
    
    def generate_task(self, current_time):
        """
        生成单个任务
        
        参数:
        - current_time: 当前时间(秒)
        
        返回:
        - Task: 生成的任务对象，None表示没有生成任务
        """
        # 根据概率决定是否生成任务
        if random.random() > self.task_rate:
            return None
        
        # 随机选择任务地点
        location = random.choice(self.delivery_nodes)
        
        # 随机生成货物重量
        weight = random.uniform(self.min_weight, self.max_weight)
        weight = round(weight, 2)  # 保留两位小数
        
        # 生成截止时间
        deadline = None
        if random.random() < self.deadline_rate:
            # 截止时间在1-6小时之间
            deadline_delta = random.randint(3600, 21600)
            deadline = current_time + deadline_delta
        
        # 创建任务
        task = Task(
            task_id=self.task_id_counter,
            location=location,
            weight=weight,
            start_time=current_time,
            deadline=deadline
        )
        
        self.task_id_counter += 1
        return task
    
    def generate_tasks(self, current_time, num_tasks=None):
        """
        生成多个任务
        
        参数:
        - current_time: 当前时间(秒)
        - num_tasks: 生成任务的数量，None表示根据概率随机生成
        
        返回:
        - list: 生成的任务列表
        """
        tasks = []
        
        if num_tasks is not None:
            # 生成指定数量的任务
            for _ in range(num_tasks):
                location = random.choice(self.delivery_nodes)
                weight = random.uniform(self.min_weight, self.max_weight)
                weight = round(weight, 2)
                
                deadline = None
                if random.random() < self.deadline_rate:
                    deadline_delta = random.randint(3600, 21600)
                    deadline = current_time + deadline_delta
                
                task = Task(
                    task_id=self.task_id_counter,
                    location=location,
                    weight=weight,
                    start_time=current_time,
                    deadline=deadline
                )
                
                tasks.append(task)
                self.task_id_counter += 1
        else:
            # 根据概率生成任务
            task = self.generate_task(current_time)
            if task:
                tasks.append(task)
        
        return tasks
    
    def generate_large_task(self, current_time):
        """
        生成大型任务(需要多车协同)
        
        参数:
        - current_time: 当前时间(秒)
        
        返回:
        - Task: 生成的大型任务对象
        """
        # 选择繁忙区域
        busy_nodes = [1, 3, 6, 10, 11]  # 天河体育中心、珠江新城、北京路、广州塔、琶洲
        location = random.choice(busy_nodes)
        
        # 生成大型货物(1000-3000kg)
        weight = random.uniform(1000, 3000)
        weight = round(weight, 2)
        
        # 大型任务通常有截止时间
        deadline_delta = random.randint(3600, 14400)  # 1-4小时
        deadline = current_time + deadline_delta
        
        # 创建任务
        task = Task(
            task_id=self.task_id_counter,
            location=location,
            weight=weight,
            start_time=current_time,
            deadline=deadline
        )
        
        self.task_id_counter += 1
        return task

if __name__ == "__main__":
    # 测试任务类
    from data.guangzhou_map import create_guangzhou_graph
    
    # 创建地图
    G = create_guangzhou_graph()
    
    # 创建任务生成器
    generator = TaskGenerator(G, task_rate=1.0)  # 设置概率为1.0确保生成任务
    
    # 生成任务
    current_time = 0
    tasks = generator.generate_tasks(current_time, num_tasks=5)
    
    print(f"生成了 {len(tasks)} 个任务:")
    for task in tasks:
        deadline_str = f"{task.deadline}秒" if task.deadline else "无"
        print(f"- 任务{task.id}: 位置=节点{task.location}, 重量={task.weight}kg, 截止时间={deadline_str}")
    
    # 测试任务评分
    test_task = tasks[0]
    test_task.completion_time = current_time + 1800  # 30分钟完成
    test_task.total_distance = 15000  # 15公里
    test_task.waiting_time = 600  # 10分钟等待
    
    score = test_task.calculate_score()
    print(f"\n任务{test_task.id}评分: {score:.1f}")
    print("评分详情:")
    for key, value in test_task.score_details.items():
        print(f"  {key}: {value:.1f}")
    
    # 测试任务失败
    fail_task = tasks[1]
    fail_task.fail(current_time + 3600)  # 1小时后失败
    
    print(f"\n任务{fail_task.id}失败扣分: {fail_task.score:.1f}")