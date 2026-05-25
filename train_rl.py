import argparse
import json
import random
import statistics

from app import run_fast_simulation
from gurobi_optimizer import solve_static_oracle
from rl_agent import MODEL_PATH, RL_ACTIONS, ExpertSelector, RLDispatchStrategy
from simulator import Simulator


def run_training_episode(agent, config, seed):
    random.seed(seed)
    sim = Simulator(
        fleet_size=config["fleet_size"],
        simulation_time=config["simulation_time"],
        task_rate=config["task_rate"],
        strategy_name="balanced",
        node_count=config["node_count"],
    )
    sim.strategy = agent

    while sim.current_time < sim.simulation_time:
        before_score = sim.total_score
        before_completed = sim.completed_task_count
        before_failed = sim.failed_task_count

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

        score_delta = sim.total_score - before_score
        completed_delta = sim.completed_task_count - before_completed
        failed_delta = sim.failed_task_count - before_failed
        reward = score_delta + completed_delta * 8 - failed_delta * 15

        idle_vehicle = next((vehicle for vehicle in sim.fleet if vehicle.status == "idle"), sim.fleet[0])
        pending = [task for task in sim.tasks if task.status == "pending"]
        next_state = agent.encode_state(idle_vehicle, pending, sim.map)
        agent.learn_from_step(reward, next_state)

    return {
        "total_tasks": sim.total_tasks,
        "completed_tasks": sim.completed_task_count,
        "failed_tasks": sim.failed_task_count,
        "total_score": sim.total_score,
    }


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


def best_action_for_oracle_task(vehicle, available_tasks, map_model, target_task):
    matching_actions = []
    for action in RL_ACTIONS:
        selected = ExpertSelector.select(action, vehicle, available_tasks, map_model)
        if selected is not None and selected.id == target_task.id:
            matching_actions.append(action)
    if matching_actions:
        return matching_actions[0]

    path = map_model.shortest_path(vehicle.current_location, target_task.location)
    if not path:
        return None
    target_distance = map_model.calculate_distance(path)
    best_action = None
    best_gap = None
    for action in RL_ACTIONS:
        selected = ExpertSelector.select(action, vehicle, available_tasks, map_model)
        if selected is None:
            continue
        selected_path = map_model.shortest_path(vehicle.current_location, selected.location)
        if not selected_path:
            continue
        selected_distance = map_model.calculate_distance(selected_path)
        gap = abs(selected_distance - target_distance)
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_action = action
    return best_action


def pretrain_from_gurobi(agent, config, seed, episodes, time_limit, task_limit):
    rows = []
    for episode in range(episodes):
        random.seed(seed + episode)
        sim = Simulator(
            fleet_size=config["fleet_size"],
            simulation_time=config["simulation_time"],
            task_rate=config["task_rate"],
            strategy_name="balanced",
            node_count=config["node_count"],
        )
        tasks = generate_static_tasks(sim)
        result = solve_static_oracle(
            sim.map,
            sim.fleet,
            tasks,
            config["simulation_time"],
            time_limit=time_limit,
            task_limit=task_limit,
        )
        if result.get("status") not in ("optimal", "time_limited") or not result.get("plan"):
            print(f"gurobi pretrain {episode + 1}/{episodes} skipped: {result.get('message')}")
            continue

        tasks_by_id = {task.id: task for task in tasks}
        served = set()
        learned = 0
        for vehicle_plan in result["plan"]:
            vehicle = next((v for v in sim.fleet if v.id == vehicle_plan["vehicle_id"]), None)
            if vehicle is None:
                continue
            dispatch_time = 0
            for stop in vehicle_plan["route"]:
                target = tasks_by_id.get(stop["task_id"])
                if target is None:
                    continue
                sim.map.current_time = dispatch_time
                available = [
                    task for task in tasks
                    if task.id not in served and task.start_time <= max(dispatch_time, target.start_time)
                ]
                if target not in available:
                    available.append(target)
                state = agent.encode_state(vehicle, available, sim.map)
                action = best_action_for_oracle_task(vehicle, available, sim.map, target)
                if action:
                    agent.reinforce_action(state, action, 35 + max(0, stop.get("score", 0)) / 5)
                    learned += 1

                path = sim.map.shortest_path(vehicle.current_location, target.location)
                if path:
                    vehicle.current_location = target.location
                dispatch_time = stop["arrival_time"]
                served.add(target.id)

        rows.append({
            "score": result.get("total_score", 0) or 0,
            "completed": result.get("completed_tasks", 0),
            "failed": result.get("failed_tasks", 0),
            "tasks": len(tasks),
            "learned": learned,
            "status": result.get("status"),
        })
        total_score = result.get("total_score", 0) or 0
        print(
            f"gurobi pretrain {episode + 1:>3}/{episodes} | "
            f"status={result.get('status')} | tasks={len(tasks)} | "
            f"completed={result.get('completed_tasks', 0)} | learned={learned} | "
            f"score={total_score:.1f}"
        )
    return rows


def evaluate_strategy(strategy_name, config, seeds):
    rows = []
    for seed in seeds:
        random.seed(seed)
        sim = Simulator(
            fleet_size=config["fleet_size"],
            simulation_time=config["simulation_time"],
            task_rate=config["task_rate"],
            strategy_name=strategy_name,
            node_count=config["node_count"],
        )
        run_fast_simulation(sim)
        rows.append({
            "score": sim.total_score,
            "completed": sim.completed_task_count,
            "failed": sim.failed_task_count,
            "tasks": sim.total_tasks,
        })
    return summarize(rows)


def summarize(rows):
    return {
        "episodes": len(rows),
        "avg_score": statistics.mean(row.get("score", row.get("total_score", 0)) for row in rows),
        "avg_completed": statistics.mean(row.get("completed", row.get("completed_tasks", 0)) for row in rows),
        "avg_failed": statistics.mean(row.get("failed", row.get("failed_tasks", 0)) for row in rows),
        "avg_tasks": statistics.mean(row.get("tasks", row.get("total_tasks", 0)) for row in rows),
    }


def main():
    parser = argparse.ArgumentParser(description="Train the EV dispatch RL policy with tabular Q-learning.")
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--eval-runs", type=int, default=8)
    parser.add_argument("--model-path", default=MODEL_PATH)
    parser.add_argument("--fleet-size", type=int, default=8)
    parser.add_argument("--simulation-time", type=int, default=1800)
    parser.add_argument("--task-rate", type=float, default=0.12)
    parser.add_argument("--node-count", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gurobi-pretrain", action="store_true")
    parser.add_argument("--gurobi-episodes", type=int, default=8)
    parser.add_argument("--gurobi-time-limit", type=int, default=20)
    parser.add_argument("--gurobi-task-limit", type=int, default=24)
    args = parser.parse_args()

    config = {
        "fleet_size": args.fleet_size,
        "simulation_time": args.simulation_time,
        "task_rate": args.task_rate,
        "node_count": args.node_count,
    }

    agent = RLDispatchStrategy(
        model_path=args.model_path,
        epsilon=0.35,
        learning_rate=0.18,
        discount=0.9,
    )
    pretrain_rows = []
    if args.gurobi_pretrain:
        pretrain_config = dict(config)
        pretrain_config["simulation_time"] = min(config["simulation_time"], 900)
        pretrain_config["task_rate"] = min(config["task_rate"], 0.08)
        pretrain_config["fleet_size"] = min(config["fleet_size"], 6)
        pretrain_config["node_count"] = min(config["node_count"], 16)
        pretrain_rows = pretrain_from_gurobi(
            agent,
            pretrain_config,
            args.seed + 50000,
            args.gurobi_episodes,
            args.gurobi_time_limit,
            args.gurobi_task_limit,
        )

    training_rows = []
    for episode in range(args.episodes):
        progress = episode / max(args.episodes - 1, 1)
        agent.epsilon = max(0.04, 0.35 * (1 - progress))
        row = run_training_episode(agent, config, args.seed + episode)
        training_rows.append(row)
        if (episode + 1) % max(1, args.episodes // 10) == 0:
            recent = summarize(training_rows[-max(1, args.episodes // 10):])
            print(
                f"episode {episode + 1:>4}/{args.episodes} | "
                f"epsilon={agent.epsilon:.3f} | "
                f"avg_score={recent['avg_score']:.1f} | "
                f"avg_failed={recent['avg_failed']:.1f}"
            )

    eval_seeds = [args.seed + 10000 + index for index in range(args.eval_runs)]
    agent.epsilon = 0.0
    agent.save(args.model_path, meta={
        "config": config,
        "episodes": args.episodes,
        "seed": args.seed,
        "gurobi_pretrain": {
            "enabled": args.gurobi_pretrain,
            "episodes": args.gurobi_episodes,
            "time_limit": args.gurobi_time_limit,
            "task_limit": args.gurobi_task_limit,
            "summary": summarize(pretrain_rows) if pretrain_rows else None,
        },
        "training_summary": summarize(training_rows),
    })

    report = {
        "rl": evaluate_strategy("rl", config, eval_seeds),
        "balanced": evaluate_strategy("balanced", config, eval_seeds),
        "nearest": evaluate_strategy("nearest", config, eval_seeds),
        "max_weight": evaluate_strategy("max_weight", config, eval_seeds),
        "urgency": evaluate_strategy("urgency", config, eval_seeds),
        "model_path": args.model_path,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
