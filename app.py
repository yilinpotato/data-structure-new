from flask import Flask, render_template, jsonify, request, redirect, url_for
import threading
import time
import json
import os
from simulator import GuangzhouMap, Simulator

app = Flask(__name__)

# 全局状态
simulation_running = False
simulation_thread = None
current_state = {}
simulator = None

def map_payload(map_model):
    return {
        'nodes': map_model.nodes,
        'edges': map_model.adjacency_list,
        'charging_stations': [
            {
                'id': s.id,
                'node_id': s.node_id,
                'capacity': s.capacity,
                'occupied': len(s.occupied),
                'queue': len(s.queue)
            }
            for s in map_model.charging_stations
        ]
    }

# 预设地图数据（用于初始化显示）
default_map_data = map_payload(GuangzhouMap(node_count=24))

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
    node_count = data.get('node_count', 24)
    
    simulator = Simulator(
        fleet_size=fleet_size,
        simulation_time=simulation_time,
        task_rate=task_rate,
        strategy_name=strategy,
        node_count=node_count
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
        return jsonify(map_payload(simulator.map))
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
                    'path_progress': v.path_progress,
                    'path_distance': v.total_path_distance,
                    'distance_remaining': v.distance_remaining
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
            'details': simulator.get_detail_statistics(),
            'charging_stations': [
                {'id': s.id, 'occupied': len(s.occupied), 'queue': len(s.queue), 'capacity': s.capacity}
                for s in simulator.map.charging_stations
            ],
            'statistics': {
                'total_tasks': simulator.total_tasks,
                'completed_tasks': simulator.completed_task_count,
                'failed_tasks': simulator.failed_task_count,
                'completion_rate': (simulator.completed_task_count / max(simulator.total_tasks, 1)) * 100,
                'total_score': simulator.total_score,
                'active_vehicles': sum(1 for v in simulator.fleet if v.status != 'idle'),
                'charging_vehicles': sum(len(s.occupied) for s in simulator.map.charging_stations),
                'waiting_vehicles': sum(len(s.queue) for s in simulator.map.charging_stations)
            }
        }
        
        simulator.current_time += simulator.time_step
        time.sleep(0.3)
    
    simulation_running = False

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
