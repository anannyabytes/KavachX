from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from .planning_engine import _as_frame


def _frame(items: pd.DataFrame | Iterable[dict[str, Any]]) -> pd.DataFrame:
    return items.copy() if isinstance(items, pd.DataFrame) else pd.DataFrame(list(items))


def _timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["_start"] = pd.to_datetime(result["date"].astype(str) + " " + result["start_time"].astype(str), errors="raise")
    result["_end"] = pd.to_datetime(result["date"].astype(str) + " " + result["end_time"].astype(str), errors="raise")
    if (result["_end"] <= result["_start"]).any():
        raise ValueError("Every maintenance window must end after it starts.")
    return result


def _overlaps(left: pd.Series, right: pd.Series) -> bool:
    return left["_start"] < right["_end"] and right["_start"] < left["_end"]


def calculate_comparison(original_requests: pd.DataFrame | Iterable[dict[str, Any]], optimized_blocks: pd.DataFrame | Iterable[dict[str, Any]], train_windows: pd.DataFrame | Iterable[dict[str, Any]] | None = None, scenario_days: int = 30) -> pd.DataFrame:
    """Calculate blocks, conflicts, downtime and availability from actual inputs."""
    before = _timestamps(_frame(original_requests))
    after = _timestamps(_as_frame(optimized_blocks))
    trains = _frame(train_windows) if train_windows is not None else pd.DataFrame()
    if not trains.empty:
        trains = _timestamps(trains)

    def conflicts(windows: pd.DataFrame) -> int:
        count = 0
        records = list(windows.iterrows())
        for position, (_, left) in enumerate(records):
            for _, right in records[position + 1:]:
                if left["corridor_id"] == right["corridor_id"] and _overlaps(left, right):
                    count += 1
            for _, train in trains.iterrows():
                if left["corridor_id"] == train["corridor_id"] and _overlaps(left, train):
                    count += 1
        return count

    def hours(windows: pd.DataFrame) -> float:
        return round((windows["_end"] - windows["_start"]).dt.total_seconds().sum() / 3600, 2) if not windows.empty else 0.0

    dates = pd.concat([before["_start"], after["_start"]])
    days = max(scenario_days, int((dates.max().normalize() - dates.min().normalize()).days + 1)) if not dates.empty else scenario_days
    before_hours, after_hours = hours(before), hours(after)
    return pd.DataFrame([
        {"metric": "Separate maintenance blocks", "Before KavachX": len(before), "KavachX": len(after)},
        {"metric": "Detected conflicts", "Before KavachX": conflicts(before), "KavachX": conflicts(after)},
        {"metric": "Estimated downtime (hours)", "Before KavachX": before_hours, "KavachX": after_hours},
        {"metric": "Asset availability (%)", "Before KavachX": round(100 * (1 - before_hours / (days * 24)), 2), "KavachX": round(100 * (1 - after_hours / (days * 24)), 2)},
    ])
