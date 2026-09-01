"""
data_loader.py – Railway Maintenance Data Loader Module
=========================================================
Loads synthetic datasets (from JSON or CSV) into Pandas DataFrames,
parses time columns into datetime.time objects, and prepares unified
data structures for downstream priority and scheduling optimization engines.
"""

import os
import json
import datetime
import pandas as pd
from typing import Dict, Any, Union


def get_default_data_dir() -> str:
    """Returns the base data directory path relative to repository root."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "data")


def load_synthetic_json(json_path: str = None) -> Dict[str, Any]:
    """
    Loads raw synthetic data dictionary from synthetic_data.json.
    """
    if json_path is None:
        json_path = os.path.join(get_default_data_dir(), "synthetic_data.json")

    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Synthetic data file not found at: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _convert_time_column(df: pd.DataFrame, col_name: str) -> pd.DataFrame:
    """Helper function to convert %H:%M time string column to datetime.time objects."""
    if col_name in df.columns:
        # Handle string HH:MM values gracefully
        def parse_val(v):
            if isinstance(v, str):
                parts = v.split(":")
                return datetime.time(int(parts[0]), int(parts[1]))
            elif isinstance(v, datetime.time):
                return v
            return v

        df[col_name] = df[col_name].apply(parse_val)
    return df


def load_all_data(data_dir: str = None) -> Dict[str, pd.DataFrame]:
    """
    Reads all maintenance and traffic datasets, converts time columns into
    Python datetime.time objects (%H:%M format), concatenates maintenance task
    DataFrames into a master 'all_tasks' DataFrame, and returns a dictionary of DataFrames.
    """
    if data_dir is None:
        data_dir = get_default_data_dir()

    json_path = os.path.join(data_dir, "synthetic_data.json")

    # If synthetic_data.json exists, load from JSON; otherwise try CSV files
    if os.path.exists(json_path):
        raw_data = load_synthetic_json(json_path)
        tms_df = pd.DataFrame(raw_data.get("tms", []))
        smms_df = pd.DataFrame(raw_data.get("smms", []))
        tdms_df = pd.DataFrame(raw_data.get("tdms", []))
        bdms_df = pd.DataFrame(raw_data.get("bdms", []))
        coa_df = pd.DataFrame(raw_data.get("coa", []))
        timetable_df = pd.DataFrame(raw_data.get("timetable", []))
        goods_df = pd.DataFrame(raw_data.get("goods_forecast", []))
    else:
        tms_df = pd.read_csv(os.path.join(data_dir, "tms.csv"))
        smms_df = pd.read_csv(os.path.join(data_dir, "smms.csv"))
        tdms_df = pd.read_csv(os.path.join(data_dir, "tdms.csv"))
        bdms_df = pd.read_csv(os.path.join(data_dir, "bdms.csv"))
        coa_df = pd.read_csv(os.path.join(data_dir, "coa.csv"))
        timetable_df = pd.read_csv(os.path.join(data_dir, "timetable.csv"))
        goods_df = pd.read_csv(os.path.join(data_dir, "goods_forecast.csv"))

    # Convert time columns into datetime.time objects
    bdms_df = _convert_time_column(bdms_df, "requested_start")
    bdms_df = _convert_time_column(bdms_df, "requested_end")

    coa_df = _convert_time_column(coa_df, "available_start")
    coa_df = _convert_time_column(coa_df, "available_end")

    timetable_df = _convert_time_column(timetable_df, "arrival_time")
    timetable_df = _convert_time_column(timetable_df, "departure_time")

    goods_df = _convert_time_column(goods_df, "expected_start")
    goods_df = _convert_time_column(goods_df, "expected_end")

    # Concatenate maintenance tables into master all_tasks DataFrame
    all_tasks_df = pd.concat([tms_df, smms_df, tdms_df], ignore_index=True)

    return {
        "tms": tms_df,
        "smms": smms_df,
        "tdms": tdms_df,
        "all_tasks": all_tasks_df,
        "bdms": bdms_df,
        "coa": coa_df,
        "timetable": timetable_df,
        "goods_forecast": goods_df,
    }


def get_golden_demo_data(data_dir: str = None) -> Dict[str, pd.DataFrame]:
    """
    Returns filtered datasets specifically for the Golden Demo scenario (Corridor C101 on 2026-09-01).
    """
    datasets = load_all_data(data_dir)
    c101_tasks = datasets["all_tasks"][datasets["all_tasks"]["corridor_id"] == "C101"]
    c101_bdms = datasets["bdms"][datasets["bdms"]["corridor_id"] == "C101"]
    c101_coa = datasets["coa"][
        (datasets["coa"]["corridor_id"] == "C101") & (datasets["coa"]["date"] == "2026-09-01")
    ]
    c101_trains = datasets["timetable"][datasets["timetable"]["corridor_id"] == "C101"]
    c101_goods = datasets["goods_forecast"][datasets["goods_forecast"]["corridor_id"] == "C101"]

    return {
        "tasks": c101_tasks,
        "bdms": c101_bdms,
        "coa": c101_coa,
        "trains": c101_trains,
        "goods": c101_goods,
    }


if __name__ == "__main__":
    print("=== Testing data_loader.py ===")
    datasets = load_all_data()
    for key, df in datasets.items():
        print(f"Dataset '{key}': {len(df)} rows, columns: {list(df.columns)}")

    golden = get_golden_demo_data()
    print(f"\nGolden Demo Golden Tasks on C101: {len(golden['tasks'])} tasks loaded.")
