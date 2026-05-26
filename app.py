from flask import Flask, render_template, jsonify, request, redirect, url_for
import threading
import time
import json
import os
import random
import math
from simulator import GuangzhouMap, Simulator
from gurobi_optimizer import solve_static_oracle

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

def clean_json_value(value):
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: clean_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_json_value(item) for item in value]
    return value

# 预设地图数据（用于初始化显示）
default_map_data = map_payload(GuangzhouMap(node_count=24))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_simulation', methods=['POST'])
def start_simulation():
    global simulation_running, simulation_thread, current_state, simulator
    
    if simulation_running:
        return jsonify({"status": "error", "message": "模拟已在运行中"})
    
    data = request.get_json()
    fleet_size = data.get('fleet_size', 10)
    simulation_time = data.get('simulation_time', 3600)
    task_rate = data.get('task_rate', 0.01)
    strategy = data.get('strategy', 'nearest')
    node_count = data.get('node_count', 24)
    seed = data.get('seed')
    
    simulator = Simulator(
        fleet_size=fleet_size,
        simulation_time=simulation_time,
        task_rate=task_rate,
        strategy_name=strategy,
        node_count=node_count,
        seed=seed
    )
    current_state = build_current_state()
    
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

@app.route('/run_all_strategies', methods=['POST'])
def run_all_strategies():
    global simulation_running
    if simulation_running:
        return jsonify({"status": "error", "message": "请先停止实时模拟，再一键跑完所有策略"})

    data = request.get_json()
    fleet_size = int(data.get('fleet_size', 10))
    simulation_time = int(data.get('simulation_time', 3600))
    task_rate = float(data.get('task_rate', 0.01))
    node_count = int(data.get('node_count', 24))
    seed = int(data.get('seed', 42))
    gurobi_time_limit = int(data.get('gurobi_time_limit', 180))

    strategies = [
        ("nearest", "最近任务优先"),
        ("max_weight", "最大任务优先"),
        ("urgency", "紧急任务优先"),
        ("balanced", "平衡策略"),
        ("rl", "Q学习策略"),
        ("ppo", "PPO强化学习策略")
    ]
    results = []

    for strategy_name, label in strategies:
        random.seed(seed)
        sim = Simulator(
            fleet_size=fleet_size,
            simulation_time=simulation_time,
            task_rate=task_rate,
            strategy_name=strategy_name,
            node_count=node_count,
            seed=seed
        )
        run_fast_simulation(sim)
        details = sim.get_detail_statistics()
        results.append({
            "strategy": strategy_name,
            "label": label,
            "status": "success",
            "total_tasks": sim.total_tasks,
            "completed_tasks": sim.completed_task_count,
            "failed_tasks": sim.failed_task_count,
            "completion_rate": (sim.completed_task_count / max(sim.total_tasks, 1)) * 100,
            "total_score": sim.total_score,
            "average_task_score": details["average_task_score"],
            "average_task_time": details["average_task_time"],
            "charging_count": details["charging_count"],
            "coordinated_dispatch_count": details["coordinated_dispatch_count"]
        })

    random.seed(seed)
    oracle_sim = Simulator(
        fleet_size=fleet_size,
        simulation_time=simulation_time,
        task_rate=task_rate,
        strategy_name="balanced",
        node_count=node_count,
        seed=seed
    )
    oracle_tasks = generate_static_tasks(oracle_sim)
    oracle_result = solve_static_oracle(
        oracle_sim.map,
        oracle_sim.fleet,
        oracle_tasks,
        simulation_time,
        time_limit=gurobi_time_limit,
        task_limit=None,
        mip_gap=0.05
    )
    optimized_tasks = oracle_result.get("optimized_tasks") or 0
    if oracle_result.get("status") == "optimal" and oracle_result.get("unoptimized_tasks", 0) == 0:
        oracle_label = "Gurobi静态最优"
    elif oracle_result.get("status") == "gap_accepted":
        oracle_label = "Gurobi近似最优(<5%)"
    elif oracle_result.get("status") == "time_limited":
        oracle_label = "Gurobi精确求解(未证明)"
    else:
        oracle_label = "Gurobi精确求解(子问题)"
    results.append({
        "strategy": "gurobi_oracle",
        "label": oracle_label,
        "status": oracle_result["status"],
        "message": oracle_result["message"],
        "total_tasks": optimized_tasks,
        "generated_tasks": len(oracle_tasks),
        "optimized_tasks": optimized_tasks,
        "unoptimized_tasks": oracle_result.get("unoptimized_tasks"),
        "completed_tasks": oracle_result["completed_tasks"],
        "failed_tasks": oracle_result.get("failed_tasks", 0),
        "completion_rate": (oracle_result["completed_tasks"] / max(optimized_tasks, 1)) * 100,
        "total_score": oracle_result["total_score"],
        "average_task_score": (oracle_result.get("total_task_score", 0) / oracle_result["completed_tasks"])
            if oracle_result["completed_tasks"] else None,
        "average_task_time": None,
        "charging_count": None,
        "coordinated_dispatch_count": None,
        "mip_gap": oracle_result.get("mip_gap"),
        "model_bound": oracle_result.get("model_bound"),
        "gurobi_time_limit": gurobi_time_limit,
        "plan": oracle_result.get("plan", [])[:5]
    })

    best_dynamic = max(
        [
            r for r in results
            if r.get("strategy") != "gurobi_oracle" and isinstance(r.get("total_score"), (int, float))
        ],
        key=lambda row: row["total_score"],
        default=None
    )
    best_overall = max(
        [r for r in results if isinstance(r.get("total_score"), (int, float))],
        key=lambda row: row["total_score"],
        default=None
    )
    payload = {
        "status": "success",
        "seed": seed,
        "best_strategy": best_dynamic["label"] if best_dynamic else None,
        "best_overall": best_overall["label"] if best_overall else None,
        "results": results
    }
    return jsonify(clean_json_value(payload))

def generate_static_tasks(sim):
    tasks = []
    while sim.current_time < sim.simulation_time:
        for _ in range(3):
            new_task = sim._generate_task()
            if new_task:
                tasks.append(new_task)
        sim.current_time += sim.time_step
    sim.current_time = 0
    return tasks

def run_fast_simulation(sim):
    while sim.current_time < sim.simulation_time:
        for _ in range(3):
            new_task = sim._generate_task()
            if new_task:
                sim.tasks.append(new_task)
                sim.total_tasks += 1

        sim._update_vehicle_states()
        sim._check_task_deadlines()
        sim._allocate_tasks()
        sim._manage_charging()
        sim._record_station_loads()
        sim.map.current_time = sim.current_time
        sim.current_time += sim.time_step

    return sim

def build_current_state():
    if simulator is None:
        return {}

    return {
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
        simulator._record_station_loads()
        
        current_state = build_current_state()
        
        simulator.current_time += simulator.time_step
        time.sleep(0.3)
    
    simulation_running = False

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000, use_reloader=False)
