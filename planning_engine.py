"""Person 5: weekly and 30-day plan generation from optimizer output."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _as_frame(optimized_blocks: pd.DataFrame | Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Accept a DataFrame or optimizer list output and validate its core fields."""
    frame = optimized_blocks.copy() if isinstance(optimized_blocks, pd.DataFrame) else pd.DataFrame(list(optimized_blocks))
    if frame.empty:
        return frame
    aliases = {
        "block_date": "date", "scheduled_date": "date", "start": "start_time",
        "end": "end_time", "tasks": "activities", "task_names": "activities",
        "department": "departments", "corridor": "corridor_id",
    }
    frame = frame.rename(columns={old: new for old, new in aliases.items() if old in frame and new not in frame})
    missing = {"corridor_id", "date", "start_time", "end_time"} - set(frame.columns)
    if missing:
        raise ValueError(f"Optimized blocks missing required fields: {', '.join(sorted(missing))}")
    return frame


def _display_list(value: Any) -> str:
    """Format list-valued departments or activities for a dashboard table."""
    if isinstance(value, (list, tuple, set)):
        return " + ".join(map(str, value))
    return "" if pd.isna(value) else str(value)


def build_weekly_plan(optimized_blocks: pd.DataFrame | Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Produce a day-of-week operational table from Person 4's scheduled blocks."""
    blocks = _as_frame(optimized_blocks)
    columns = ["day", "date", "start", "end", "corridor", "departments", "activities", "priority", "status"]
    if blocks.empty:
        return pd.DataFrame(columns=columns)

    blocks["date"] = pd.to_datetime(blocks["date"], errors="raise")
    blocks["_start_sort"] = pd.to_datetime(blocks["date"].dt.strftime("%Y-%m-%d") + " " + blocks["start_time"].astype(str), errors="raise")
    blocks["day"] = pd.Categorical(blocks["date"].dt.day_name(), categories=WEEKDAY_ORDER, ordered=True)
    plan = pd.DataFrame({
        "day": blocks["day"], "date": blocks["date"].dt.strftime("%d %b %Y"),
        "start": blocks["start_time"].astype(str), "end": blocks["end_time"].astype(str),
        "corridor": blocks["corridor_id"],
        "departments": blocks.get("departments", pd.Series("Coordinated", index=blocks.index)).map(_display_list),
        "activities": blocks.get("activities", pd.Series("Maintenance", index=blocks.index)).map(_display_list),
        "priority": blocks.get("priority", pd.Series("Normal", index=blocks.index)),
        "status": blocks.get("status", pd.Series("Planned", index=blocks.index)),
        "_start_sort": blocks["_start_sort"],
    })
    return plan.sort_values(["day", "_start_sort", "corridor"], kind="stable").drop(columns="_start_sort").reset_index(drop=True)


def build_monthly_plan(optimized_blocks: pd.DataFrame | Iterable[dict[str, Any]], start_date: str | None = None) -> pd.DataFrame:
    """Produce a 30-day, one-line-per-corridor-per-week strategic roll-up."""
    blocks = _as_frame(optimized_blocks)
    columns = ["week", "corridor", "departments", "activities", "blocks", "first_date", "last_date"]
    if blocks.empty:
        return pd.DataFrame(columns=columns)

    blocks["date"] = pd.to_datetime(blocks["date"], errors="raise").dt.normalize()
    scenario_start = pd.Timestamp(start_date).normalize() if start_date else blocks["date"].min()
    blocks = blocks[(blocks["date"] >= scenario_start) & (blocks["date"] < scenario_start + pd.Timedelta(days=30))].copy()
    if blocks.empty:
        return pd.DataFrame(columns=columns)
    blocks["week_number"] = ((blocks["date"] - scenario_start).dt.days // 7) + 1

    def joined(values: pd.Series) -> str:
        values_seen = []
        for value in values:
            for item in _display_list(value).split(" + "):
                if item and item not in values_seen:
                    values_seen.append(item)
        return " + ".join(values_seen)

    summary = blocks.groupby(["week_number", "corridor_id"], as_index=False).agg(
        departments=("departments", joined) if "departments" in blocks else ("corridor_id", lambda _: "Coordinated"),
        activities=("activities", joined) if "activities" in blocks else ("corridor_id", lambda _: "Maintenance"),
        blocks=("corridor_id", "size"), first_date=("date", "min"), last_date=("date", "max"),
    )
    summary["week"] = "Week " + summary.pop("week_number").astype(str)
    summary = summary.rename(columns={"corridor_id": "corridor"})
    summary["first_date"] = summary["first_date"].dt.strftime("%d %b")
    summary["last_date"] = summary["last_date"].dt.strftime("%d %b")
    return summary[["week", "corridor", "departments", "activities", "blocks", "first_date", "last_date"]]


def weekly_gantt_data(optimized_blocks: pd.DataFrame | Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Return start/end timestamps for an optional Gantt-style dashboard chart."""
    blocks = _as_frame(optimized_blocks)
    if blocks.empty:
        return pd.DataFrame(columns=["corridor_id", "departments", "start", "end", "priority"])
    dates = pd.to_datetime(blocks["date"]).dt.strftime("%Y-%m-%d")
    return pd.DataFrame({
        "corridor_id": blocks["corridor_id"],
        "departments": blocks.get("departments", pd.Series("Coordinated", index=blocks.index)).map(_display_list),
        "start": pd.to_datetime(dates + " " + blocks["start_time"].astype(str)),
        "end": pd.to_datetime(dates + " " + blocks["end_time"].astype(str)),
        "priority": blocks.get("priority", pd.Series("Normal", index=blocks.index)),
    })
