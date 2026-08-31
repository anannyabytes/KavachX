"""
optimizer.py – Schedule Optimization Prototype
================================================
Uses Google OR-Tools CP-SAT solver to select an optimal set of
task windows (bundled or individual) to maximize maintenance
throughput while respecting safety, corridor, and resource rules.
"""

import collections
from typing import Any, Dict, List
from ortools.sat.python import cp_model


def _parse_time(t_str: str) -> int:
    """Convert HH:MM to minutes since midnight for intervals."""
    h, m = map(int, t_str.split(':'))
    return h * 60 + m


def optimize_schedule(
    bundled_windows: List[Dict[str, Any]],
    individual_windows: List[Dict[str, Any]],
    task_meta: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Selects optimal candidate windows.

    Parameters
    ----------
    bundled_windows:
        List of merged candidate windows (e.g. from bundling.py).
    individual_windows:
        List of single-task windows.
    task_meta:
        Dict mapping task_id -> metadata, e.g.
        {'priority': 'high', 'resources': ['tamping-machine-A']}

    Returns
    -------
    dict
        Solver status, objective value, and selected windows.
    """
    model = cp_model.CpModel()

    # Consolidate all candidates into a single list
    candidates = []
    for i, w in enumerate(bundled_windows):
        candidates.append({'id': f"b_{i}", 'is_bundled': True, 'data': w})
    for i, w in enumerate(individual_windows):
        candidates.append({'id': f"i_{i}", 'is_bundled': False, 'data': w})

    # Trackers for constraints
    task_presence = collections.defaultdict(list)
    corridor_intervals = collections.defaultdict(list)
    resource_intervals = collections.defaultdict(list)

    selections = {}
    objective_terms = []

    for cand in candidates:
        c_id = cand['id']
        w = cand['data']
        is_bundled = cand['is_bundled']

        # Decision Variable: Is this window selected?
        b = model.NewBoolVar(f"select_{c_id}")
        selections[c_id] = b

        start_m = _parse_time(w['start_time'])
        end_m = _parse_time(w['end_time'])
        duration = end_m - start_m

        # Interval Variable
        interval = model.NewOptionalIntervalVar(
            start_m, duration, end_m, b, f"interval_{c_id}"
        )

        # Corridor grouping (No overlapping intervals on the same corridor)
        corridor_intervals[w['corridor_id']].append(interval)

        score = 0
        task_ids = w.get('tasks', [w.get('task_id')]) if is_bundled else [w.get('task_id')]

        for tid in task_ids:
            if not tid:
                continue
            task_presence[tid].append(b)
            meta = task_meta.get(tid, {})

            # Resource grouping
            for res in meta.get('resources', []):
                resource_intervals[res].append(interval)

            # Objective: Priority-weighted maintenance (duration * weight)
            # High priority = weight 10, normal = weight 1
            weight = 10 if meta.get('priority') == 'high' else 1
            score += duration * weight

        # Bundling Rewards / Penalties
        if is_bundled:
            # Reward selecting bundled multi-department blocks
            score += 500 * len(task_ids)
        else:
            # Penalize the number of separate possessions
            score -= 100

        objective_terms.append(score * b)

    # Constraint 1: High-priority must be assigned exactly once, others at most once
    for tid, bool_vars in task_presence.items():
        meta = task_meta.get(tid, {})
        if meta.get('priority') == 'high':
            model.AddExactlyOne(bool_vars)
        else:
            model.AddAtMostOne(bool_vars)

    # Constraint 2: No overlapping intervals on the same corridor
    for corr, intervals in corridor_intervals.items():
        if len(intervals) > 1:
            model.AddNoOverlap(intervals)

    # Constraint 3: Resource non-overlap
    for res, intervals in resource_intervals.items():
        if len(intervals) > 1:
            model.AddNoOverlap(intervals)

    # Objective Function
    model.Maximize(sum(objective_terms))

    # Solve
    solver = cp_model.CpSolver()
    # Keep the model small so it solves in under 2 seconds
    solver.parameters.max_time_in_seconds = 2.0
    status = solver.Solve(model)

    result = {
        "status": solver.StatusName(status),
        "objective_value": solver.ObjectiveValue(),
        "selected_windows": []
    }

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for cand in candidates:
            c_id = cand['id']
            if solver.Value(selections[c_id]):
                result["selected_windows"].append(cand['data'])

    return result


if __name__ == "__main__":
    # Synthetic Demo Scenario
    bundled_demo = [
        {
            "corridor_id": "C-101",
            "start_time": "13:00",
            "end_time": "16:00",
            "tasks": ["ENG-401", "SIG-205", "TRX-112"],
            "departments": ["Engineering", "S&T", "Traction"]
        }
    ]

    individual_demo = [
        {
            "task_id": "ENG-401",
            "corridor_id": "C-101",
            "start_time": "13:00",
            "end_time": "15:00",
            "department": "Engineering"
        },
        {
            "task_id": "SIG-205",
            "corridor_id": "C-101",
            "start_time": "13:30",
            "end_time": "15:00",
            "department": "S&T"
        },
        {
            "task_id": "TRX-112",
            "corridor_id": "C-101",
            "start_time": "14:00",
            "end_time": "16:00",
            "department": "Traction"
        }
    ]

    meta_demo = {
        "ENG-401": {"priority": "high", "resources": ["tamping-machine-A"]},
        "SIG-205": {"priority": "normal", "resources": ["signal-testing-rig-3"]},
        "TRX-112": {"priority": "high", "resources": ["ohe-inspection-car-1"]},
    }

    res = optimize_schedule(bundled_demo, individual_demo, meta_demo)
    
    import json
    print(json.dumps(res, indent=2))
