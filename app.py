from flask import Flask, render_template, jsonify, request, redirect, url_for
import threading
import time
import json
import os

app = Flask(__name__)

# 全局状态
simulation_running = False
simulation_thread = None
current_state = {}
simulator = None

# 预设地图数据（用于初始化显示）
default_map_data = {
    'nodes': {
        1: {"name": "天河体育中心", "location": (23.1349, 113.3308), "pos": (400, 150)},
        2: {"name": "广州东站", "location": (23.1297, 113.3215), "pos": (380, 180)},
        3: {"name": "珠江新城", "location": (23.1233, 113.3394), "pos": (450, 200)},
        4: {"name": "天河CBD", "location": (23.1405, 113.3366), "pos": (420, 120)},
        5: {"name": "白云山南门", "location": (23.1520, 113.3240), "pos": (360, 80)},
        6: {"name": "北京路", "location": (23.1187, 113.2824), "pos": (280, 250)},
        7: {"name": "广州火车站", "location": (23.1066, 113.2658), "pos": (250, 300)},
        8: {"name": "中山纪念堂", "location": (23.1239, 113.2878), "pos": (320, 270)},
        9: {"name": "广州起义纪念馆", "location": (23.1153, 113.2785), "pos": (270, 280)},
        10: {"name": "广州塔", "location": (23.1060, 113.3245), "pos": (380, 380)},
        11: {"name": "琶洲会展中心", "location": (23.0669, 113.3350), "pos": (420, 420)},
        12: {"name": "海珠广场", "location": (23.0942, 113.2998), "pos": (340, 340)},
        13: {"name": "大学城", "location": (23.0569, 113.3237), "pos": (380, 480)},
        14: {"name": "上下九", "location": (23.1027, 113.2564), "pos": (220, 350)},
        15: {"name": "陈家祠", "location": (23.1120, 113.2518), "pos": (200, 320)},
        16: {"name": "沙面", "location": (23.0924, 113.2527), "pos": (200, 380)},
        100: {"name": "中央仓库", "location": (23.1550, 113.3500), "pos": (500, 100)}
    },
    'edges': {
        1: [(2, 1500), (3, 2000), (4, 1000), (6, 5000)],
        2: [(1, 1500), (8, 4000), (5, 3000)],
        3: [(1, 2000), (10, 3000), (4, 1500)],
        4: [(1, 1000), (3, 1500), (100, 2000)],
        5: [(2, 3000)],
        6: [(1, 5000), (8, 2000), (12, 3000)],
        7: [(8, 2000), (14, 3000)],
        8: [(2, 4000), (6, 2000), (7, 2000), (15, 3000)],
        9: [(8, 2000), (15, 3000)],
        10: [(3, 3000), (11, 5000), (12, 5000)],
        11: [(10, 5000), (13, 6000)],
        12: [(6, 3000), (10, 5000), (16, 2000)],
        13: [(11, 6000)],
        14: [(7, 3000), (15, 2000), (16, 2000)],
        15: [(8, 3000), (14, 2000)],
        16: [(12, 2000), (14, 2000)],
        100: [(4, 2000)]
    },
    'charging_stations': [
        {'id': 1, 'node_id': 1, 'capacity': 10, 'occupied': 0, 'queue': 0},
        {'id': 2, 'node_id': 3, 'capacity': 8, 'occupied': 0, 'queue': 0},
        {'id': 3, 'node_id': 6, 'capacity': 6, 'occupied': 0, 'queue': 0},
        {'id': 4, 'node_id': 10, 'capacity': 12, 'occupied': 0, 'queue': 0},
        {'id': 5, 'node_id': 14, 'capacity': 6, 'occupied': 0, 'queue': 0},
        {'id': 6, 'node_id': 100, 'capacity': 5, 'occupied': 0, 'queue': 0}
    ]
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_simulation', methods=['POST'])
def start_simulation():
    global simulation_running, simulation_thread, simulator
    
    if simulation_running:
        return jsonify({"status": "error", "message": "模拟已在运行中"})
    
    data = request.get_json()
    fleet_size = data.get('fleet_size', 10)
    simulation_time = data.get('simulation_time', 3600)
    task_rate = data.get('task_rate', 0.01)
    strategy = data.get('strategy', 'nearest')
    
    from simulator import Simulator
    simulator = Simulator(
        fleet_size=fleet_size,
        simulation_time=simulation_time,
        task_rate=task_rate,
        strategy_name=strategy
    )
    
    simulation_running = True
    simulation_thread = threading.Thread(target=run_simulation, daemon=True)
    simulation_thread.start()
    
    return jsonify({"status": "success", "message": "模拟已启动"})

@app.route('/stop_simulation', methods=['POST'])
def stop_simulation():
    global simulation_running
    simulation_running = False
    return jsonify({"status": "success", "message": "模拟已停止"})

@app.route('/get_state')
def get_state():
    global current_state
    return jsonify(current_state)

@app.route('/get_graph_data')
def get_graph_data():
    if simulator:
        return jsonify({
            'nodes': simulator.map.nodes,
            'edges': simulator.map.adjacency_list,
            'charging_stations': [
                {'id': s.id, 'node_id': s.node_id, 'capacity': s.capacity, 'occupied': len(s.occupied), 'queue': len(s.queue)}
                for s in simulator.map.charging_stations
            ]
        })
    return jsonify(default_map_data)

def run_simulation():
    global simulation_running, current_state, simulator
    
    while simulation_running and simulator.current_time < simulator.simulation_time:
        for _ in range(3):
            new_task = simulator._generate_task()
            if new_task:
                simulator.tasks.append(new_task)
                simulator.total_tasks += 1
        
        simulator._update_vehicle_states()
        simulator._check_task_deadlines()
        simulator._allocate_tasks()
        simulator._manage_charging()
        
        current_state = {
            'current_time': simulator.current_time,
            'vehicles': [
                {
                    'id': v.id,
                    'location': v.current_location,
                    'status': v.status,
                    'battery': v.get_remaining_battery(),
                    'capacity': v.capacity,
                    'current_task': v.current_task.id if v.current_task else None,
                    'path': v.current_path,
                    'path_progress': v.path_progress
                }
                for v in simulator.fleet
            ],
            'tasks': [
                {
                    'id': t.id,
                    'location': t.location,
                    'weight': t.weight,
                    'status': t.status,
                    'start_time': t.start_time,
                    'deadline': t.deadline,
                    'score': t.score
                }
                for t in simulator.tasks
            ],
            'completed_tasks': simulator.completed_task_count,
            'failed_tasks': simulator.failed_task_count,
            'total_score': simulator.total_score,
            'statistics': {
                'total_tasks': simulator.total_tasks,
                'completed_tasks': simulator.completed_task_count,
                'failed_tasks': simulator.failed_task_count,
                'completion_rate': (simulator.completed_task_count / max(simulator.total_tasks, 1)) * 100,
                'total_score': simulator.total_score,
                'active_vehicles': sum(1 for v in simulator.fleet if v.status != 'idle')
            }
        }
        
        simulator.current_time += simulator.time_step
        time.sleep(0.3)
    
    simulation_running = False

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
