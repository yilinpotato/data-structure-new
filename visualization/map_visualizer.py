"""
地图可视化模块
使用Folium和Leaflet.js实现广州市地图和车辆行驶动画
"""

import folium
import json
import numpy as np
from folium.plugins import MarkerCluster, HeatMap, TimestampedGeoJson
from folium.features import DivIcon, Popup
import branca.colormap as cm

from data.guangzhou_map import (
    create_guangzhou_graph, get_node_coordinates, get_node_name,
    get_all_charging_stations, GUANGZHOU_BOUNDARY
)
from models.vehicle import VehicleStatus
from models.task import TaskStatus

class MapVisualizer:
    """
    地图可视化类
    """
    def __init__(self, graph=None, center_lat=23.12, center_lon=113.30, zoom_start=12):
        """
        初始化地图可视化
        
        参数:
        - graph: 道路网络图
        - center_lat: 地图中心纬度
        - center_lon: 地图中心经度
        - zoom_start: 初始缩放级别
        """
        # 初始化地图
        self.map = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom_start,
            tiles='OpenStreetMap',
            control_scale=True
        )
        
        # 添加比例尺
        folium.plugins.MiniMap().add_to(self.map)
        
        # 如果没有提供图，创建一个
        self.graph = graph if graph else create_guangzhou_graph()
        
        # 颜色映射
        self.status_colors = {
            VehicleStatus.IDLE: 'green',
            VehicleStatus.MOVING: 'blue',
            VehicleStatus.CHARGING: 'yellow',
            VehicleStatus.DELIVERING: 'orange',
            VehicleStatus.COOPERATIVE: 'purple',
            VehicleStatus.RETURNING: 'red'
        }
        
        self.task_status_colors = {
            TaskStatus.PENDING: 'red',
            TaskStatus.ASSIGNED: 'orange',
            TaskStatus.IN_PROGRESS: 'blue',
            TaskStatus.COMPLETED: 'green',
            TaskStatus.FAILED: 'black',
            TaskStatus.COOPERATIVE: 'purple'
        }
        
        # 图标设置
        self.vehicle_icons = {
            VehicleStatus.IDLE: 'truck',
            VehicleStatus.MOVING: 'truck',
            VehicleStatus.CHARGING: 'bolt',
            VehicleStatus.DELIVERING: 'truck-loading',
            VehicleStatus.COOPERATIVE: 'truck-loading',
            VehicleStatus.RETURNING: 'truck'
        }
        
        # 标记层
        self.vehicle_markers = {}
        self.task_markers = {}
        self.station_markers = {}
        
        # 添加图层控制
        self.feature_group = folium.FeatureGroup(name='道路网络')
        self.vehicle_group = folium.FeatureGroup(name='车辆')
        self.task_group = folium.FeatureGroup(name='任务')
        self.station_group = folium.FeatureGroup(name='充电站')
        
        # 添加图层到地图
        self.feature_group.add_to(self.map)
        self.vehicle_group.add_to(self.map)
        self.task_group.add_to(self.map)
        self.station_group.add_to(self.map)
        
        # 添加图层控制
        folium.LayerControl().add_to(self.map)
    
    def add_road_network(self, show_labels=False):
        """
        添加道路网络到地图
        
        参数:
        - show_labels: 是否显示道路标签
        """
        # 添加节点
        for node_id in self.graph.nodes:
            lat, lon = get_node_coordinates(node_id)
            if lat and lon:
                # 添加节点标记
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=2,
                    color='gray',
                    fill=True,
                    fill_color='gray',
                    fill_opacity=0.6,
                    tooltip=f"节点{node_id}"
                ).add_to(self.feature_group)
                
                # 添加节点标签
                if show_labels:
                    node_name = get_node_name(node_id)
                    folium.Marker(
                        location=[lat, lon],
                        icon=DivIcon(
                            icon_size=(150, 36),
                            icon_anchor=(0, 0),
                            html=f'<div style="font-size: 10pt">{node_name}</div>'
                        ),
                        tooltip=f"节点{node_id}: {node_name}"
                    ).add_to(self.feature_group)
        
        # 添加边（道路）
        for u, v, data in self.graph.edges(data=True):
            u_lat, u_lon = get_node_coordinates(u)
            v_lat, v_lon = get_node_coordinates(v)
            
            if u_lat and u_lon and v_lat and v_lon:
                # 根据道路类型设置颜色和宽度
                road_type = data.get('road_type', '普通道路')
                if road_type == '高速路':
                    color = '#ff0000'
                    weight = 4
                elif road_type == '快速路':
                    color = '#ff8800'
                    weight = 3
                elif road_type == '主干道':
                    color = '#0000ff'
                    weight = 3
                else:
                    color = '#000000'
                    weight = 2
                
                # 添加道路
                folium.PolyLine(
                    locations=[[u_lat, u_lon], [v_lat, v_lon]],
                    color=color,
                    weight=weight,
                    opacity=0.6,
                    tooltip=f"{data.get('road_name', '道路')} ({data.get('weight', 0)}m)"
                ).add_to(self.feature_group)
    
    def add_charging_stations(self, stations=None):
        """
        添加充电站到地图
        
        参数:
        - stations: 充电站列表，如果为None则使用默认充电站
        """
        if stations is None:
            stations = get_all_charging_stations()
        
        for station in stations:
            lat, lon = station['location']
            
            # 创建充电站标记
            popup_html = f"""
            <div style="font-size: 12pt">
            <b>{station['name']}</b><br>
            ID: {station['id']}<br>
            充电桩: {station['capacity']}个<br>
            充电速率: {station['charging_rate']} km/分钟
            </div>
            """
            
            # 添加充电站圆形标记
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color='blue',
                fill=True,
                fill_color='blue',
                fill_opacity=0.3,
                popup=popup_html,
                tooltip=f"{station['name']}"
            ).add_to(self.station_group)
            
            # 保存标记引用
            self.station_markers[station['id']] = {
                'location': [lat, lon],
                'popup': popup_html
            }
    
    def update_charging_stations(self, stations):
        """
        更新充电站状态
        
        参数:
        - stations: 充电站列表
        """
        # 清除现有充电站标记
        self.station_group._children = {}
        
        # 重新添加充电站
        for station in stations:
            lat, lon = station['location']
            
            # 创建充电站标记
            popup_html = f"""
            <div style="font-size: 12pt">
            <b>{station['name']}</b><br>
            ID: {station['id']}<br>
            充电桩: {station['capacity']}个<br>
            充电速率: {station['charging_rate']} km/分钟<br>
            占用: {station['occupied']}/{station['capacity']}<br>
            排队: {station['queue_length']}辆
            </div>
            """
            
            # 根据占用率设置颜色
            utilization = station['occupied'] / station['capacity'] if station['capacity'] > 0 else 0
            if utilization > 0.8:
                color = 'red'
            elif utilization > 0.5:
                color = 'orange'
            else:
                color = 'green'
            
            # 添加充电站圆形标记
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.3,
                popup=popup_html,
                tooltip=f"{station['name']} (占用率: {utilization:.1%})"
            ).add_to(self.station_group)
    
    def add_vehicles(self, vehicles):
        """
        添加车辆到地图
        
        参数:
        - vehicles: 车辆列表
        """
        for vehicle in vehicles:
            if vehicle.current_location:
                lat, lon = get_node_coordinates(vehicle.current_location)
                
                # 创建车辆标记
                popup_html = f"""
                <div style="font-size: 12pt">
                <b>车辆{vehicle.id}</b><br>
                状态: {vehicle.status.value}<br>
                电量: {vehicle.current_battery:.1f}/{vehicle.max_battery} km<br>
                载重: {vehicle.capacity} kg<br>
                总行驶: {vehicle.total_distance/1000:.1f} km<br>
                完成任务: {vehicle.total_tasks} 个
                </div>
                """
                
                # 获取状态对应的颜色和图标
                color = self.status_colors.get(vehicle.status, 'gray')
                icon = self.vehicle_icons.get(vehicle.status, 'truck')
                
                # 添加车辆标记
                marker = folium.Marker(
                    location=[lat, lon],
                    icon=folium.Icon(color=color, icon=icon, prefix='fa'),
                    popup=popup_html,
                    tooltip=f"车辆{vehicle.id} ({vehicle.status.value})"
                )
                marker.add_to(self.vehicle_group)
                
                # 保存标记引用
                self.vehicle_markers[vehicle.id] = marker
    
    def update_vehicles(self, vehicles):
        """
        更新车辆位置和状态
        
        参数:
        - vehicles: 车辆列表
        """
        # 清除现有车辆标记
        self.vehicle_group._children = {}
        
        # 重新添加车辆
        for vehicle in vehicles:
            if vehicle.current_location:
                lat, lon = get_node_coordinates(vehicle.current_location)
                
                # 创建车辆标记
                popup_html = f"""
                <div style="font-size: 12pt">
                <b>车辆{vehicle.id}</b><br>
                状态: {vehicle.status.value}<br>
                电量: {vehicle.current_battery:.1f}/{vehicle.max_battery} km<br>
                载重: {vehicle.capacity} kg<br>
                总行驶: {vehicle.total_distance/1000:.1f} km<br>
                完成任务: {vehicle.total_tasks} 个
                """
                
                # 如果有当前任务，添加任务信息
                if vehicle.current_task:
                    popup_html += f"""<br>
                    当前任务: {vehicle.current_task.id}<br>
                    目的地: {get_node_name(vehicle.current_task.location)}
                    """
                
                popup_html += "</div>"
                
                # 获取状态对应的颜色和图标
                color = self.status_colors.get(vehicle.status, 'gray')
                icon = self.vehicle_icons.get(vehicle.status, 'truck')
                
                # 添加车辆标记
                marker = folium.Marker(
                    location=[lat, lon],
                    icon=folium.Icon(color=color, icon=icon, prefix='fa'),
                    popup=popup_html,
                    tooltip=f"车辆{vehicle.id} ({vehicle.status.value})"
                )
                marker.add_to(self.vehicle_group)
    
    def add_tasks(self, tasks):
        """
        添加任务到地图
        
        参数:
        - tasks: 任务列表
        """
        for task in tasks:
            if task.location:
                lat, lon = get_node_coordinates(task.location)
                
                # 创建任务标记
                popup_html = f"""
                <div style="font-size: 12pt">
                <b>任务{task.id}</b><br>
                状态: {task.status.value}<br>
                重量: {task.weight:.1f} kg<br>
                位置: {get_node_name(task.location)}
                """
                
                # 如果有截止时间，添加截止时间
                if task.deadline:
                    deadline_str = f"{(task.deadline/3600):.1f}小时"
                    popup_html += f"<br>截止时间: {deadline_str}"
                
                # 如果已分配车辆，添加车辆信息
                if task.assigned_vehicles:
                    vehicle_ids = [v.id for v in task.assigned_vehicles]
                    popup_html += f"<br>分配车辆: {', '.join(map(str, vehicle_ids))}"
                
                popup_html += "</div>"
                
                # 根据任务状态设置颜色
                color = self.task_status_colors.get(task.status, 'gray')
                
                # 根据货物重量设置大小
                radius = min(10, max(5, task.weight / 100))
                
                # 添加任务圆形标记
                marker = folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.6,
                    popup=popup_html,
                    tooltip=f"任务{task.id} ({task.status.value})"
                )
                marker.add_to(self.task_group)
                
                # 保存标记引用
                self.task_markers[task.id] = marker
    
    def update_tasks(self, tasks):
        """
        更新任务状态
        
        参数:
        - tasks: 任务列表
        """
        # 清除现有任务标记
        self.task_group._children = {}
        
        # 重新添加任务
        for task in tasks:
            if task.location:
                lat, lon = get_node_coordinates(task.location)
                
                # 创建任务标记
                popup_html = f"""
                <div style="font-size: 12pt">
                <b>任务{task.id}</b><br>
                状态: {task.status.value}<br>
                重量: {task.weight:.1f} kg<br>
                位置: {get_node_name(task.location)}
                """
                
                # 如果有截止时间，添加截止时间
                if task.deadline:
                    deadline_str = f"{(task.deadline/3600):.1f}小时"
                    popup_html += f"<br>截止时间: {deadline_str}"
                
                # 如果已分配车辆，添加车辆信息
                if task.assigned_vehicles:
                    vehicle_ids = [v.id for v in task.assigned_vehicles]
                    popup_html += f"<br>分配车辆: {', '.join(map(str, vehicle_ids))}"
                
                # 如果已完成，添加完成信息
                if task.status == TaskStatus.COMPLETED:
                    completion_time = f"{(task.completion_time - task.start_time)/60:.1f}分钟"
                    popup_html += f"<br>完成时间: {completion_time}"
                    popup_html += f"<br>评分: {task.score:.1f}"
                
                popup_html += "</div>"
                
                # 根据任务状态设置颜色
                color = self.task_status_colors.get(task.status, 'gray')
                
                # 根据货物重量设置大小
                radius = min(10, max(5, task.weight / 100))
                
                # 添加任务圆形标记
                marker = folium.CircleMarker(
                    location=[lat, lon],
                    radius=radius,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.6,
                    popup=popup_html,
                    tooltip=f"任务{task.id} ({task.status.value})"
                )
                marker.add_to(self.task_group)
    
    def create_vehicle_animation(self, vehicle_data, task_data, station_data, filename='animation.html'):
        """
        创建车辆行驶动画
        
        参数:
        - vehicle_data: 车辆数据列表
        - task_data: 任务数据列表
        - station_data: 充电站数据列表
        - filename: 输出文件名
        """
        # 首先添加道路网络
        self.add_road_network(show_labels=False)
        
        # 准备GeoJSON数据
        features = []
        
        # 添加车辆轨迹
        for vehicle in vehicle_data:
            if 'path' in vehicle and vehicle['path'] and len(vehicle['path']) > 1:
                # 获取路径的所有坐标点
                path_coordinates = []
                for node_id in vehicle['path']:
                    lat, lon = get_node_coordinates(node_id)
                    if lat and lon:
                        path_coordinates.append([lat, lon])
                
                # 绘制路径线
                if len(path_coordinates) > 1:
                    # 获取状态对应的颜色
                    status = vehicle.get('status', 'idle')
                    color = self.status_colors.get(VehicleStatus(status), 'gray')
                    
                    # 添加路径线
                    folium.PolyLine(
                        locations=path_coordinates,
                        color=color,
                        weight=3,
                        opacity=0.7,
                        popup=f"车辆{vehicle['id']}的路径"
                    ).add_to(self.vehicle_group)
                
                # 为路径中的每个点创建时间戳，实现平滑动画
                # 增加中间点，使动画更平滑
                for i in range(len(vehicle['path']) - 1):
                    start_node = vehicle['path'][i]
                    end_node = vehicle['path'][i+1]
                    
                    start_lat, start_lon = get_node_coordinates(start_node)
                    end_lat, end_lon = get_node_coordinates(end_node)
                    
                    if start_lat and start_lon and end_lat and end_lon:
                        # 计算两点之间的距离
                        import math
                        distance = math.sqrt((end_lat - start_lat)**2 + (end_lon - start_lon)**2)
                        
                        # 根据距离确定中间点数量，距离越远中间点越多
                        num_intermediate = max(2, int(distance * 10000))  # 每0.1度约11公里，设置适当的中间点
                        
                        # 生成中间点
                        for j in range(num_intermediate + 1):
                            # 线性插值计算中间点坐标
                            ratio = j / num_intermediate
                            current_lat = start_lat + (end_lat - start_lat) * ratio
                            current_lon = start_lon + (end_lon - start_lon) * ratio
                            
                            # 计算时间戳（实现更平滑的动画）
                            timestamp = vehicle.get('timestamp', 0) + (i * 10) + (j * 10 / num_intermediate)
                            
                            # 获取状态对应的颜色
                            status = vehicle.get('status', 'idle')
                            color = self.status_colors.get(VehicleStatus(status), 'gray')
                            
                            # 创建GeoJSON特征
                            feature = {
                                "type": "Feature",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [current_lon, current_lat]
                                },
                                "properties": {
                                    "time": timestamp,
                                    "icon": "circle",
                                    "iconstyle": {
                                        "color": color,
                                        "fillColor": color,
                                        "fillOpacity": 0.8,
                                        "radius": 6,
                                        "stroke": True,
                                        "weight": 2
                                    },
                                    "popup": f"车辆{vehicle['id']} - {status}"
                                }
                            }
                            features.append(feature)
        
        # 创建TimestampedGeoJson
        timestamped_geo_json = TimestampedGeoJson(
            {
                "type": "FeatureCollection",
                "features": features
            },
            period="PT1S",  # 每1秒更新一次，实现更平滑的动画
            add_last_point=True,
            auto_play=True,  # 自动播放
            loop=False,
            max_speed=10,
            time_slider_drag_update=True
        )
        timestamped_geo_json.add_to(self.map)
        
        # 添加当前任务标记
        for task in task_data:
            if task['status'] in ['pending', 'assigned', 'in_progress']:
                lat, lon = task['location']
                
                # 根据任务状态设置颜色
                status = task.get('status', 'pending')
                color = self.task_status_colors.get(TaskStatus(status), 'gray')
                
                # 添加任务标记
                folium.CircleMarker(
                    location=[lat, lon],
                    radius=5,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.6,
                    popup=f"任务{task['id']} - {status}"
                ).add_to(self.task_group)
        
        # 添加充电站标记
        for station in station_data:
            lat, lon = station['location']
            
            # 添加充电站标记
            folium.CircleMarker(
                location=[lat, lon],
                radius=8,
                color='blue',
                fill=True,
                fill_color='blue',
                fill_opacity=0.3,
                popup=f"充电站{station['id']} - 占用: {station['occupied']}/{station['capacity']}"
            ).add_to(self.station_group)
        
        # 保存地图
        self.map.save(filename)
        print(f"动画已保存到 {filename}")
    
    def create_simulation_map(self, simulator, filename='simulation_map.html'):
        """
        创建模拟地图
        
        参数:
        - simulator: 模拟器实例
        - filename: 输出文件名
        """
        # 添加道路网络
        self.add_road_network(show_labels=True)
        
        # 添加充电站
        self.add_charging_stations()
        
        # 更新车辆和任务
        self.update_vehicles(simulator.fleet)
        self.update_tasks(simulator.tasks)
        
        # 添加统计信息
        stats_html = f"""
        <div style="font-size: 12pt; background-color: white; padding: 10px; border-radius: 5px;">
        <h3>模拟统计</h3>
        <p>当前时间: {simulator.current_time/3600:.1f}小时</p>
        <p>待处理任务: {len(simulator.tasks)}</p>
        <p>已完成任务: {len(simulator.completed_tasks)}</p>
        <p>失败任务: {len(simulator.failed_tasks)}</p>
        <p>总评分: {simulator.total_score:.1f}</p>
        <p>车辆利用率: {simulator.vehicle_utilization*100:.1f}%</p>
        <p>充电站利用率: {simulator.charging_station_utilization*100:.1f}%</p>
        </div>
        """
        
        # 添加统计信息到地图
        folium.Marker(
            location=[GUANGZHOU_BOUNDARY['north'], GUANGZHOU_BOUNDARY['west']],
            icon=DivIcon(
                icon_size=(300, 200),
                icon_anchor=(0, 0),
                html=stats_html
            ),
            tooltip="模拟统计"
        ).add_to(self.map)
        
        # 保存地图
        self.map.save(filename)
        print(f"模拟地图已保存到 {filename}")
    
    def create_animated_simulation(self, simulator, filename='animated_simulation.html'):
        """
        创建动画模拟
        
        参数:
        - simulator: 模拟器实例
        - filename: 输出文件名
        """
        # 添加道路网络
        self.add_road_network()
        
        # 添加充电站
        self.add_charging_stations()
        
        # 准备动画数据，使用车辆历史路径数据
        vehicle_data = []
        
        # 先添加历史路径数据
        for history_item in simulator.vehicle_history:
            if history_item['path'] and len(history_item['path']) > 1:
                vehicle_data.append(history_item)
        
        # 再添加当前路径数据，确保动画包含最新状态
        for vehicle in simulator.fleet:
            if vehicle.current_path and len(vehicle.current_path) > 1:
                # 检查是否已经添加过这个路径
                already_added = False
                for item in vehicle_data:
                    if item['id'] == vehicle.id and item['path'] == vehicle.current_path:
                        already_added = True
                        break
                
                if not already_added:
                    vehicle_data.append({
                        'id': vehicle.id,
                        'path': vehicle.current_path,
                        'status': vehicle.status.value,
                        'timestamp': simulator.current_time
                    })
        
        # 创建动画
        self.create_vehicle_animation(
            vehicle_data,
            simulator.visualization_data['tasks'],
            simulator.visualization_data['charging_stations'],
            filename
        )
    
    def save_map(self, filename='map.html'):
        """
        保存地图到文件
        
        参数:
        - filename: 输出文件名
        """
        self.map.save(filename)
        print(f"地图已保存到 {filename}")

if __name__ == "__main__":
    # 测试地图可视化
    from models.simulator import Simulator
    
    # 创建模拟器
    simulator = Simulator(
        fleet_size=10,
        simulation_time=3600*2,  # 2小时
        task_rate=0.02,
        strategy_name="balanced"
    )
    
    # 运行模拟
    simulator.run(verbose=True)
    
    # 创建地图可视化
    visualizer = MapVisualizer(simulator.graph)
    
    # 添加道路网络
    visualizer.add_road_network(show_labels=True)
    
    # 添加充电站
    visualizer.add_charging_stations()
    
    # 更新车辆和任务
    visualizer.update_vehicles(simulator.fleet)
    visualizer.update_tasks(simulator.tasks + simulator.completed_tasks)
    
    # 保存地图
    visualizer.save_map('test_map.html')
    
    # 创建动画模拟
    visualizer.create_animated_simulation(simulator, 'test_animation.html')