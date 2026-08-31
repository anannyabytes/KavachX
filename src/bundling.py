"""
bundling.py – Railway Block-Planning Prototype
================================================
Groups pre-filtered feasible task windows by corridor and merges
overlapping / adjacent windows into consolidated proposed blocks,
subject to lightweight compatibility rules.

Output schema per block::

    {
        "corridor_id": str,
        "date": str,              # ISO-format date (YYYY-MM-DD)
        "start_time": str,        # HH:MM
        "end_time": str,          # HH:MM
        "tasks": [task_id, ...],
        "departments": [dept, ...]
    }
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TIME_FMT = "%H:%M"

# Two windows are considered "adjacent" when the gap between them is at most
# this many minutes.  Setting to 0 means only truly overlapping or abutting
# windows qualify; a small positive value lets us absorb typical rounding.
_ADJACENCY_TOLERANCE_MIN = 15


def _parse_time(t: str) -> datetime:
    """Parse an HH:MM string into a datetime (date component is irrelevant)."""
    return datetime.strptime(t, _TIME_FMT)


def _windows_overlap_or_adjacent(
    start_a: str, end_a: str,
    start_b: str, end_b: str,
) -> bool:
    """Return True when two time windows overlap or are within the adjacency
    tolerance of each other."""
    sa, ea = _parse_time(start_a), _parse_time(end_a)
    sb, eb = _parse_time(start_b), _parse_time(end_b)
    tolerance = timedelta(minutes=_ADJACENCY_TOLERANCE_MIN)
    # No overlap when one ends well before the other starts.
    return not (ea + tolerance < sb or eb + tolerance < sa)


def _safety_flags_compatible(
    flags_a: dict[str, Any],
    flags_b: dict[str, Any],
) -> bool:
    """Two tasks are incompatible when they declare *conflicting* values for
    the same safety / isolation flag.

    Examples of conflicts:
      - Task A needs ``power_off: True``, Task B needs ``power_off: False``.
      - Task A needs ``isolation_zone: "full"``, Task B needs
        ``isolation_zone: "partial"``.

    If a flag only appears in one task it is not a conflict.
    """
    shared_keys = set(flags_a) & set(flags_b)
    return all(flags_a[k] == flags_b[k] for k in shared_keys)


def _resources_conflict(
    resources_a: list[str],
    resources_b: list[str],
) -> bool:
    """Return True when two tasks demand the same exact resource, which would
    constitute a double-booking."""
    return bool(set(resources_a) & set(resources_b))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def bundle_tasks(
    feasible_windows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group feasible task windows into proposed blocks.

    Parameters
    ----------
    feasible_windows:
        Each element is a dict with **at least** the following keys:

        * ``task_id``       – unique task identifier (str)
        * ``corridor_id``   – corridor the task belongs to (str)
        * ``date``          – ISO date string, e.g. ``"2026-09-15"``
        * ``start_time``    – window start, ``"HH:MM"``
        * ``end_time``      – window end,   ``"HH:MM"``
        * ``department``    – owning department (str)
        * ``safety_flags``  – dict of safety / isolation requirements
        * ``resources``     – list of resource identifiers the task needs

    Returns
    -------
    list[dict]
        Proposed blocks matching the output schema described in the module
        docstring.
    """

    # 1. Group by (corridor_id, date) so we only merge tasks that share the
    #    same corridor on the same day.
    corridor_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for task in feasible_windows:
        key = (task["corridor_id"], task["date"])
        corridor_groups[key].append(task)

    proposed_blocks: list[dict[str, Any]] = []

    for (corridor_id, date), tasks in corridor_groups.items():
        # 2. Sort by start_time so the greedy merge sweeps left-to-right.
        tasks.sort(key=lambda t: _parse_time(t["start_time"]))

        # Each "block" is a growing accumulation of compatible tasks.
        # We maintain a list of active blocks for this corridor+date.
        blocks: list[dict[str, Any]] = []

        for task in tasks:
            merged = False

            for block in blocks:
                # 3a. Check temporal overlap / adjacency.
                if not _windows_overlap_or_adjacent(
                    block["start_time"], block["end_time"],
                    task["start_time"], task["end_time"],
                ):
                    continue

                # 3b. Check safety-flag compatibility against every task
                #     already in the block.
                if not all(
                    _safety_flags_compatible(
                        task["safety_flags"], existing["safety_flags"],
                    )
                    for existing in block["_task_objects"]
                ):
                    continue

                # 3c. Check for resource double-booking.
                if any(
                    _resources_conflict(
                        task["resources"], existing["resources"],
                    )
                    for existing in block["_task_objects"]
                ):
                    continue

                # ---- Compatible: absorb task into this block ----
                block["tasks"].append(task["task_id"])
                block["departments"].add(task["department"])
                # Expand the block window to cover the new task.
                if _parse_time(task["start_time"]) < _parse_time(
                    block["start_time"]
                ):
                    block["start_time"] = task["start_time"]
                if _parse_time(task["end_time"]) > _parse_time(
                    block["end_time"]
                ):
                    block["end_time"] = task["end_time"]
                block["_task_objects"].append(task)
                merged = True
                break  # task absorbed; move on to the next one

            if not merged:
                # Start a new block seeded with this task.
                blocks.append(
                    {
                        "corridor_id": corridor_id,
                        "date": date,
                        "start_time": task["start_time"],
                        "end_time": task["end_time"],
                        "tasks": [task["task_id"]],
                        "departments": {task["department"]},
                        "_task_objects": [task],
                    }
                )

        # 4. Finalise: convert sets -> sorted lists and drop internal fields.
        for block in blocks:
            block["departments"] = sorted(block["departments"])
            del block["_task_objects"]
            proposed_blocks.append(block)

    return proposed_blocks


# ---------------------------------------------------------------------------
# Demo / smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_windows = [
        {
            "task_id": "T-001",
            "corridor_id": "COR-WEST-01",
            "date": "2026-09-15",
            "start_time": "02:00",
            "end_time": "04:00",
            "department": "Track",
            "safety_flags": {"power_off": True, "isolation_zone": "full"},
            "resources": ["tamping-machine-A"],
        },
        {
            "task_id": "T-002",
            "corridor_id": "COR-WEST-01",
            "date": "2026-09-15",
            "start_time": "03:30",
            "end_time": "05:00",
            "department": "Signalling",
            "safety_flags": {"power_off": True, "isolation_zone": "full"},
            "resources": ["signal-testing-rig-1"],
        },
        {
            "task_id": "T-003",
            "corridor_id": "COR-WEST-01",
            "date": "2026-09-15",
            "start_time": "02:30",
            "end_time": "04:30",
            "department": "Electrical",
            "safety_flags": {"power_off": False},  # conflict with T-001/T-002
            "resources": ["ohw-inspection-car"],
        },
        {
            "task_id": "T-004",
            "corridor_id": "COR-EAST-02",
            "date": "2026-09-15",
            "start_time": "01:00",
            "end_time": "03:00",
            "department": "Track",
            "safety_flags": {"power_off": True},
            "resources": ["tamping-machine-B"],
        },
        {
            "task_id": "T-005",
            "corridor_id": "COR-EAST-02",
            "date": "2026-09-15",
            "start_time": "02:30",
            "end_time": "04:00",
            "department": "Track",
            "safety_flags": {"power_off": True},
            "resources": ["tamping-machine-B"],  # same resource -> conflict
        },
        {
            "task_id": "T-006",
            "corridor_id": "COR-EAST-02",
            "date": "2026-09-15",
            "start_time": "02:45",
            "end_time": "03:30",
            "department": "Signalling",
            "safety_flags": {"power_off": True},
            "resources": ["signal-testing-rig-2"],
        },
    ]

    blocks = bundle_tasks(sample_windows)

    import json

    print(json.dumps(blocks, indent=2))
