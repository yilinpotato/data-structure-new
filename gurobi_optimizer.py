def solve_static_oracle(map_model, fleet, tasks, simulation_time, time_limit=10, task_limit=None, mip_gap=0):
    """
    Solve a static oracle dispatch model with Gurobi.

    The oracle sees generated tasks in advance and solves the static dispatch
    MILP. A row is a proven global optimum only when Gurobi returns OPTIMAL.
    """
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except Exception as exc:
        return {
            "status": "unavailable",
            "message": f"Gurobi unavailable: {exc}",
            "total_score": None,
            "completed_tasks": 0,
            "plan": [],
        }

    sorted_tasks = sorted(tasks, key=lambda t: (t.start_time, t.id))
    if not sorted_tasks:
        return {
            "status": "optimal",
            "message": "No tasks generated for the static oracle.",
            "total_score": 0,
            "completed_tasks": 0,
            "generated_tasks": 0,
            "optimized_tasks": 0,
            "unoptimized_tasks": 0,
            "plan": [],
        }

    exact_limit = len(sorted_tasks) if task_limit is None else int(task_limit)
    exact_tasks = sorted_tasks[:exact_limit]
    warm_start = _solve_static_greedy_oracle(map_model, fleet, exact_tasks, simulation_time)

    try:
        return _solve_selected_tasks(
            gp, GRB, map_model, fleet, sorted_tasks, exact_tasks,
            simulation_time, time_limit, warm_start, mip_gap
        )
    except Exception as exc:
        return {
            "status": "failed",
            "message": f"Gurobi exact solve failed: {exc}",
            "total_score": None,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "generated_tasks": len(tasks),
            "optimized_tasks": len(exact_tasks),
            "unoptimized_tasks": max(0, len(tasks) - len(exact_tasks)),
            "plan": [],
        }


def _solve_selected_tasks(gp, GRB, map_model, fleet, all_tasks, selected_tasks, simulation_time, time_limit, warm_start=None, mip_gap=0):
    task_count = len(selected_tasks)
    vehicle_count = len(fleet)
    depot_node = 100
    speed_m_per_second = 50.0

    def node_for(index):
        return depot_node if index == 0 else selected_tasks[index - 1].location

    distances = {}
    travel_times = {}
    for i in range(task_count + 1):
        for j in range(task_count + 1):
            if i == j:
                continue
            path = map_model.shortest_path(node_for(i), node_for(j))
            distance = map_model.calculate_distance(path) if path else 10**7
            distances[i, j] = distance
            travel_times[i, j] = distance / speed_m_per_second

    model = gp.Model("ev_static_dispatch_oracle")
    model.Params.OutputFlag = 0
    model.Params.TimeLimit = time_limit
    model.Params.MIPGap = mip_gap
    model.Params.MIPFocus = 1
    model.Params.Heuristics = 0.35
    model.Params.Presolve = 2
    model.Params.Cuts = 2
    model.Params.Symmetry = 2

    candidate_arcs = set()
    for j in range(1, task_count + 1):
        latest = selected_tasks[j - 1].deadline or simulation_time
        if travel_times[0, j] <= latest:
            candidate_arcs.add((0, j))

    earliest_from_depot = {
        i: max(selected_tasks[i - 1].start_time, travel_times[0, i])
        for i in range(1, task_count + 1)
    }
    for i in range(1, task_count + 1):
        for j in range(1, task_count + 1):
            if i == j:
                continue
            latest_j = selected_tasks[j - 1].deadline or simulation_time
            earliest_j = max(selected_tasks[j - 1].start_time, earliest_from_depot[i] + travel_times[i, j])
            if earliest_j <= latest_j:
                candidate_arcs.add((i, j))

    arcs = {}
    visits = {}
    arrivals = {}
    order = {}

    for v in range(vehicle_count):
        for i, j in candidate_arcs:
            arcs[v, i, j] = model.addVar(vtype=GRB.BINARY, name=f"x_{v}_{i}_{j}")
        for t in range(1, task_count + 1):
            visits[v, t] = model.addVar(vtype=GRB.BINARY, name=f"visit_{v}_{t}")
            arrivals[v, t] = model.addVar(lb=0, ub=simulation_time, name=f"arrive_{v}_{t}")
            order[v, t] = model.addVar(lb=0, ub=task_count, name=f"order_{v}_{t}")

    served = {
        t: model.addVar(vtype=GRB.BINARY, name=f"served_{t}")
        for t in range(1, task_count + 1)
    }
    model.update()

    if warm_start:
        task_index_by_id = {
            task.id: index
            for index, task in enumerate(selected_tasks, start=1)
        }
        for key in arcs:
            arcs[key].Start = 0
        for key in visits:
            visits[key].Start = 0
        for key in arrivals:
            arrivals[key].Start = 0
        for key in served:
            served[key].Start = 0

        vehicle_index_by_id = {
            vehicle.id: index
            for index, vehicle in enumerate(fleet)
        }
        for vehicle_plan in warm_start.get("plan", []):
            vehicle_index = vehicle_index_by_id.get(vehicle_plan["vehicle_id"])
            if vehicle_index is None:
                continue
            previous = 0
            for stop in vehicle_plan["route"]:
                task_index = task_index_by_id.get(stop["task_id"])
                if task_index is None:
                    continue
                if (vehicle_index, previous, task_index) not in arcs:
                    previous = task_index
                    continue
                arcs[vehicle_index, previous, task_index].Start = 1
                visits[vehicle_index, task_index].Start = 1
                arrivals[vehicle_index, task_index].Start = stop["arrival_time"]
                served[task_index].Start = 1
                previous = task_index

    for t, task in enumerate(selected_tasks, start=1):
        model.addConstr(gp.quicksum(visits[v, t] for v in range(vehicle_count)) == served[t])
        for v, vehicle in enumerate(fleet):
            if task.weight > vehicle.capacity:
                model.addConstr(visits[v, t] == 0)

    big_m = max(simulation_time + 10**6, 10**7)
    for v in range(vehicle_count):
        depot_out = gp.quicksum(
            arcs[v, 0, j]
            for j in range(1, task_count + 1)
            if (v, 0, j) in arcs
        )
        model.addConstr(depot_out <= 1)

        for t in range(1, task_count + 1):
            incoming = gp.quicksum(
                arcs[v, i, t]
                for i in range(task_count + 1)
                if i != t and (v, i, t) in arcs
            )
            outgoing = gp.quicksum(
                arcs[v, t, j]
                for j in range(1, task_count + 1)
                if j != t and (v, t, j) in arcs
            )
            model.addConstr(incoming == visits[v, t])
            model.addConstr(outgoing <= visits[v, t])

            task = selected_tasks[t - 1]
            model.addConstr(arrivals[v, t] >= task.start_time * visits[v, t])
            if task.deadline:
                model.addConstr(arrivals[v, t] <= task.deadline + big_m * (1 - visits[v, t]))

        # One open route per vehicle: depot departure equals the number of
        # connected route components, so disjoint task cycles are forbidden.
        model.addConstr(
            depot_out ==
            gp.quicksum(visits[v, t] for t in range(1, task_count + 1)) -
            gp.quicksum(
                arcs[v, i, j]
                for i in range(1, task_count + 1)
                for j in range(1, task_count + 1)
                if i != j and (v, i, j) in arcs
            )
        )

        for j in range(1, task_count + 1):
            if (v, 0, j) in arcs:
                model.addConstr(arrivals[v, j] >= travel_times[0, j] - big_m * (1 - arcs[v, 0, j]))

        for i in range(1, task_count + 1):
            for j in range(1, task_count + 1):
                if i != j and (v, i, j) in arcs:
                    model.addConstr(
                        order[v, j] >= order[v, i] + 1 -
                        task_count * (1 - arcs[v, i, j])
                    )
                    model.addConstr(
                        arrivals[v, j] >= arrivals[v, i] + travel_times[i, j] -
                        big_m * (1 - arcs[v, i, j])
                    )

        model.addConstr(
            gp.quicksum(
                travel_times[i, j] * arcs[v, i, j]
                for (vv, i, j) in arcs
                if vv == v
            ) <= simulation_time
        )

    completion_score = gp.LinExpr()
    for v in range(vehicle_count):
        for t, task in enumerate(selected_tasks, start=1):
            incoming_distance = gp.quicksum(
                distances[i, t] * arcs[v, i, t]
                for i in range(task_count + 1)
                if i != t and (v, i, t) in arcs
            )
            weight_bonus = min(30, task.weight / 100)
            time_bonus = 50 if task.deadline else 0
            completion_score += (100 + time_bonus + weight_bonus) * visits[v, t]
            completion_score -= incoming_distance / 1000

    failure_penalty = gp.quicksum(
        100 * (1 - served[t])
        for t in range(1, task_count + 1)
        if selected_tasks[t - 1].deadline and selected_tasks[t - 1].deadline <= simulation_time
    )
    model.setObjective(completion_score - failure_penalty, GRB.MAXIMIZE)
    model.optimize()

    if model.Status not in [GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.SUBOPTIMAL]:
        raise RuntimeError(f"Gurobi ended with status {model.Status}")
    if model.SolCount == 0:
        return {
            "status": "time_limited",
            "message": "Gurobi reached the time limit before finding a feasible dispatch plan.",
            "total_score": None,
            "total_task_score": 0,
            "model_objective": None,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "task_limit": task_count,
            "generated_tasks": len(all_tasks),
            "optimized_tasks": task_count,
            "unoptimized_tasks": max(0, len(all_tasks) - task_count),
            "plan": [],
        }

    plan = []
    completed = 0
    report_score = 0
    total_task_score = 0
    served_task_ids = set()
    for v, vehicle in enumerate(fleet):
        current = 0
        route = []
        visited_guard = set()
        while True:
            next_node = None
            for j in range(1, task_count + 1):
                if (v, current, j) in arcs and arcs[v, current, j].X > 0.5:
                    next_node = j
                    break
            if next_node is None or next_node in visited_guard:
                break

            visited_guard.add(next_node)
            task = selected_tasks[next_node - 1]
            arrival = arrivals[v, next_node].X
            incoming_distance = distances[current, next_node]
            task_score = _simulator_style_score(task, arrival, incoming_distance)
            report_score += task_score
            total_task_score += task_score
            served_task_ids.add(task.id)
            route.append({
                "task_id": task.id,
                "location": task.location,
                "weight": task.weight,
                "arrival_time": arrival,
                "score": task_score,
            })
            current = next_node

        completed += len(route)
        if route:
            plan.append({
                "vehicle_id": vehicle.id,
                "route": route,
            })

    failed_count = 0
    for task in selected_tasks:
        if task.id not in served_task_ids and task.deadline and task.deadline <= simulation_time:
            report_score -= 100
            failed_count += 1

    gap = getattr(model, "MIPGap", None)
    bound = getattr(model, "ObjBound", None)
    proven_exact = model.Status == GRB.OPTIMAL and (gap is None or gap <= max(mip_gap, 1e-9))
    status = "optimal" if proven_exact and mip_gap == 0 else "gap_accepted" if proven_exact else "time_limited"
    if len(all_tasks) == task_count and status == "optimal":
        message = "Gurobi proved the global maximum score for all generated tasks."
    elif len(all_tasks) == task_count and status == "gap_accepted":
        gap_text = f", gap={gap:.4f}" if gap is not None else ""
        message = f"Gurobi accepted a high-quality incumbent within the configured gap{gap_text}."
    elif len(all_tasks) == task_count:
        gap_text = f", gap={gap:.4f}" if gap is not None else ""
        message = f"Gurobi found an incumbent but has not proved global optimality yet{gap_text}."
    else:
        message = (
            f"Gurobi solved/progressed on an exact subproblem: "
            f"{task_count}/{len(all_tasks)} generated tasks."
        )

    return {
        "status": status,
        "message": message,
        "total_score": report_score,
        "total_task_score": total_task_score,
        "model_objective": model.ObjVal,
        "model_bound": bound,
        "mip_gap": gap,
        "completed_tasks": completed,
        "failed_tasks": failed_count,
        "task_limit": task_count,
        "generated_tasks": len(all_tasks),
        "optimized_tasks": task_count,
        "unoptimized_tasks": max(0, len(all_tasks) - task_count),
        "plan": plan,
    }


def _simulator_style_score(task, completion_time, distance):
    base_score = 100
    time_bonus = 50 if task.deadline and completion_time < task.deadline else 0
    distance_penalty = min(50, distance / 1000)
    weight_bonus = min(30, task.weight / 100)
    return base_score + time_bonus - distance_penalty + weight_bonus


def _solve_static_greedy_oracle(map_model, fleet, tasks, simulation_time):
    speed_m_per_second = 50.0
    vehicle_states = {
        index: {
            "vehicle": vehicle,
            "location": 100,
            "time": 0.0,
            "route": [],
        }
        for index, vehicle in enumerate(fleet)
    }
    unserved = set(range(len(tasks)))
    total_score = 0.0
    total_task_score = 0.0
    served_task_ids = set()

    def task_priority(task):
        deadline = task.deadline if task.deadline is not None else simulation_time + 10**9
        return (deadline, task.start_time, -task.weight)

    ordered_task_indexes = sorted(range(len(tasks)), key=lambda idx: task_priority(tasks[idx]))

    made_progress = True
    while made_progress:
        made_progress = False
        best_choice = None

        for task_index in ordered_task_indexes:
            if task_index not in unserved:
                continue
            task = tasks[task_index]

            for vehicle_index, state in vehicle_states.items():
                vehicle = state["vehicle"]
                if task.weight > vehicle.capacity:
                    continue

                path = map_model.shortest_path(state["location"], task.location)
                if not path:
                    continue

                distance = map_model.calculate_distance(path)
                arrival = max(task.start_time, state["time"] + distance / speed_m_per_second)
                if arrival > simulation_time:
                    continue
                if task.deadline and arrival > task.deadline:
                    continue

                score = _simulator_style_score(task, arrival, distance)
                urgency = (
                    max(1, task.deadline - arrival)
                    if task.deadline
                    else simulation_time + 10**6
                )
                value = score * 3 - distance / 1000 - urgency / 120
                choice = (value, score, -arrival, -distance, vehicle_index, task_index, arrival, distance)
                if best_choice is None or choice > best_choice:
                    best_choice = choice

        if best_choice is None:
            break

        _, score, _, _, vehicle_index, task_index, arrival, distance = best_choice
        task = tasks[task_index]
        state = vehicle_states[vehicle_index]
        state["route"].append({
            "task_id": task.id,
            "location": task.location,
            "weight": task.weight,
            "arrival_time": arrival,
            "score": score,
        })
        state["location"] = task.location
        state["time"] = arrival
        unserved.remove(task_index)
        served_task_ids.add(task.id)
        total_score += score
        total_task_score += score
        made_progress = True

    failed_count = 0
    for task_index in unserved:
        task = tasks[task_index]
        if task.deadline and task.deadline <= simulation_time:
            failed_count += 1
            total_score -= 100

    plan = [
        {
            "vehicle_id": state["vehicle"].id,
            "route": state["route"],
        }
        for state in vehicle_states.values()
        if state["route"]
    ]

    return {
        "status": "static_oracle",
        "message": "Full static oracle plan solved over all generated tasks.",
        "total_score": total_score,
        "total_task_score": total_task_score,
        "completed_tasks": len(served_task_ids),
        "failed_tasks": failed_count,
        "task_limit": len(tasks),
        "generated_tasks": len(tasks),
        "optimized_tasks": len(tasks),
        "unoptimized_tasks": 0,
        "plan": plan,
    }
