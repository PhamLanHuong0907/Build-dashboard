"""
Phase 3 & Phase 4: Universal ETL Pipeline & Star Schema Data Warehouse Builder.
Supports:
1. Aviation Star Schema mode (when CSV has BTS Flight Operations schema)
2. Universal Star Schema mode (for ANY input CSV file + Requirement.md):
   - Deduplicates and cleans raw data
   - Builds Dim_Date from the auto-detected primary date column
   - Builds Dim_<Dimension> tables with Pareto ABC classification (Group A Top 80%, Group B 80-95%, Group C Tail 5%)
   - Builds Fact_Main with surrogate foreign keys + all numeric measures & flags
   - Exports both Parquet (data_warehouse/*.parquet) and Clean CSV (data_warehouse/csv/*.csv)
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pv
import pyarrow.parquet as pq

from src.etl.cleaning_engine import apply_cleaning_rules, extract_date_format_map


AIRLINE_NAMES = {
    "AA": "American Airlines",
    "AS": "Alaska Airlines",
    "B6": "JetBlue Airways",
    "DL": "Delta Air Lines",
    "F9": "Frontier Airlines",
    "G4": "Allegiant Air",
    "HA": "Hawaiian Airlines",
    "MQ": "Envoy Air",
    "NK": "Spirit Airlines",
    "OH": "PSA Airlines",
    "OO": "SkyWest Airlines",
    "UA": "United Airlines",
    "WN": "Southwest Airlines",
    "YX": "Republic Airways",
    "9E": "Endeavor Air",
}

MONTH_NAMES = {
    1: ("January", "Jan"),
    2: ("February", "Feb"),
    3: ("March", "Mar"),
    4: ("April", "Apr"),
    5: ("May", "May"),
    6: ("June", "Jun"),
    7: ("July", "Jul"),
    8: ("August", "Aug"),
    9: ("September", "Sep"),
    10: ("October", "Oct"),
    11: ("November", "Nov"),
    12: ("December", "Dec"),
}

DAY_NAMES = {
    1: ("Monday", "Mon"),
    2: ("Tuesday", "Tue"),
    3: ("Wednesday", "Wed"),
    4: ("Thursday", "Thu"),
    5: ("Friday", "Fri"),
    6: ("Saturday", "Sat"),
    7: ("Sunday", "Sun"),
}


def extract_hour_from_hhmm(series: pd.Series) -> pd.Series:
    vals = series.fillna(0).astype(np.int64)
    hours = vals // 100
    hours = np.where(hours == 24, 0, hours)
    hours = np.clip(hours, 0, 23)
    return pd.Series(hours, index=series.index, dtype=np.int32)


def format_hhmm_str(series: pd.Series) -> pd.Series:
    s = series.fillna(-1).astype(np.int64)
    h = np.where(s == 2400, 0, s // 100)
    m = s % 100
    return pd.Series(
        [f"{hh:02d}:{mm:02d}" if val >= 0 else "" for val, hh, mm in zip(s, h, m)],
        index=series.index,
        dtype="object",
    )


def compute_pareto_abc(df_counts: pd.DataFrame, count_col: str, group_col_name: str = "AirportGroup") -> pd.DataFrame:
    df_sorted = df_counts.sort_values(by=count_col, ascending=False).reset_index(drop=True)
    total = max(df_sorted[count_col].sum(), 1)
    df_sorted["VolumeSharePct"] = (df_sorted[count_col] * 100.0 / total).round(4)
    df_sorted["CumulativeSharePct"] = df_sorted["VolumeSharePct"].cumsum().round(4)
    prev_cum = df_sorted["CumulativeSharePct"].shift(1, fill_value=0.0)
    df_sorted[group_col_name] = np.select(
        [prev_cum < 80.0, prev_cum < 95.0],
        ["Group A (Top 80% Volume)", "Group B (Next 15% Volume)"],
        default="Group C (Tail 5% Volume)",
    )
    df_sorted[f"{group_col_name}Code"] = np.select(
        [prev_cum < 80.0, prev_cum < 95.0],
        ["A", "B"],
        default="C",
    )
    return df_sorted


def build_dim_date_from_series(fdate: pd.Series, date_str_fmt: str = "%Y-%m-%d") -> pd.DataFrame:
    valid_dates = fdate.dropna()
    if len(valid_dates) == 0:
        unique_dates = pd.date_range("2025-01-01", "2025-12-31", freq="D")
    else:
        unique_dates = pd.date_range(valid_dates.min(), valid_dates.max(), freq="D")
    dim_date = pd.DataFrame({"Date": unique_dates})
    dim_date["DateKey"] = (dim_date["Date"].dt.year * 10000 + dim_date["Date"].dt.month * 100 + dim_date["Date"].dt.day).astype(np.int32)
    dim_date["DateStr"] = dim_date["Date"].dt.strftime(date_str_fmt)
    dim_date["Year"] = dim_date["Date"].dt.year.astype(np.int32)
    dim_date["Quarter"] = dim_date["Date"].dt.quarter.astype(np.int32)
    dim_date["QuarterLabel"] = "Q" + dim_date["Quarter"].astype(str) + " " + dim_date["Year"].astype(str)
    dim_date["MonthNo"] = dim_date["Date"].dt.month.astype(np.int32)
    dim_date["MonthName"] = dim_date["MonthNo"].map(lambda m: MONTH_NAMES[m][0])
    dim_date["MonthShort"] = dim_date["MonthNo"].map(lambda m: MONTH_NAMES[m][1])
    dim_date["YearMonth"] = dim_date["Date"].dt.strftime("%Y-%m")
    dim_date["DayOfMonth"] = dim_date["Date"].dt.day.astype(np.int32)
    dim_date["DayOfWeekNo"] = (dim_date["Date"].dt.dayofweek + 1).astype(np.int32)
    dim_date["DayName"] = dim_date["DayOfWeekNo"].map(lambda d: DAY_NAMES[d][0])
    dim_date["DayShort"] = dim_date["DayOfWeekNo"].map(lambda d: DAY_NAMES[d][1])
    dim_date["WeekOfYear"] = dim_date["Date"].dt.isocalendar().week.astype(np.int32)
    dim_date["WeekendFlag"] = np.where(dim_date["DayOfWeekNo"].isin([6, 7]), "Weekend", "Weekday")
    return dim_date


def build_data_warehouse(
    workspace_dir: str,
    csv_rel_or_abs: Optional[str] = None,
    blueprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    t0 = time.time()
    root = Path(workspace_dir)
    if blueprint is None:
        bp_path = root / "config" / "project_blueprint.json"
        blueprint = json.loads(bp_path.read_text(encoding="utf-8")) if bp_path.exists() else {}

    src_csv = csv_rel_or_abs or blueprint.get("project", {}).get("source_csv", "")
    if not src_csv:
        raise FileNotFoundError("Chưa chọn file CSV để chạy ETL.")
    csv_path = Path(src_csv) if Path(src_csv).is_absolute() else (root / src_csv)

    warehouse_dir = root / "data_warehouse"
    csv_out_dir = warehouse_dir / "csv"
    reports_dir = root / "reports"
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    csv_out_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Phase 3] Loading {csv_path} via PyArrow...")
    table = pv.read_csv(str(csv_path))
    df = table.to_pandas()

    is_aviation = {"FlightDate", "Reporting_Airline", "Origin", "Dest", "DepDelay", "ArrDelay", "Cancelled", "Diverted"}.issubset(set(df.columns))
    if not is_aviation:
        return _build_universal_star_schema(df, blueprint, warehouse_dir, csv_out_dir, reports_dir, t0)

    # --- AVIATION STAR SCHEMA BUILDER ---
    n_source = len(df)
    nat_key_cols = ["FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime"]
    dup_mask = df.duplicated(subset=nat_key_cols, keep="first")
    n_dups = int(dup_mask.sum())
    if n_dups > 0:
        df = df.loc[~dup_mask].reset_index(drop=True)
    n_clean = len(df)

    df["FlightKey"] = np.arange(1, n_clean + 1, dtype=np.int64)
    fdate = pd.to_datetime(df["FlightDate"], errors="coerce")
    df["DateKey"] = (fdate.dt.year * 10000 + fdate.dt.month * 100 + fdate.dt.day).astype(np.int32)
    df["FlightYear"] = fdate.dt.year.astype(np.int32)
    df["FlightMonthNo"] = fdate.dt.month.astype(np.int32)

    df["Origin"] = df["Origin"].astype(str).str.strip()
    df["Dest"] = df["Dest"].astype(str).str.strip()
    df["Reporting_Airline"] = df["Reporting_Airline"].astype(str).str.strip()
    df["RouteKey"] = df["Origin"] + "-" + df["Dest"]
    df["Route"] = df["Origin"] + " → " + df["Dest"]

    df["DepHour"] = extract_hour_from_hhmm(df["CRSDepTime"])
    df["ArrHour"] = extract_hour_from_hhmm(df["CRSArrTime"])
    df["CRSDepTimeFormatted"] = format_hhmm_str(df["CRSDepTime"])
    df["CRSArrTimeFormatted"] = format_hhmm_str(df["CRSArrTime"])

    dep_h = df["DepHour"].to_numpy()
    df["DepTimeBlock"] = np.select([dep_h <= 5, dep_h <= 11, dep_h <= 17], ["Early Morning", "Morning", "Afternoon"], default="Evening/Night")
    df["DepTimeBlockSort"] = np.select([dep_h <= 5, dep_h <= 11, dep_h <= 17], [1, 2, 3], default=4).astype(np.int32)

    dist = df["Distance"].fillna(0).to_numpy()
    df["DistanceBand"] = np.select([dist < 500, dist <= 1500], ["Short-haul", "Medium-haul"], default="Long-haul")
    df["DistanceBandSort"] = np.select([dist < 500, dist <= 1500], [1, 2], default=3).astype(np.int32)

    is_cancelled = (df["Cancelled"].fillna(0) == 1).astype(np.int32)
    is_diverted = ((is_cancelled == 0) & (df["Diverted"].fillna(0) == 1)).astype(np.int32)
    is_operated = ((is_cancelled == 0) & (df["DepTime"].notna() | df["WheelsOff"].notna())).astype(np.int32)
    is_completed = ((is_cancelled == 0) & (is_diverted == 0) & df["ArrTime"].notna() & df["ArrDelay"].notna() & df["ActualElapsedTime"].notna()).astype(np.int32)

    df["IsCancelled"] = is_cancelled
    df["IsDiverted"] = is_diverted
    df["IsOperated"] = is_operated
    df["IsCompletedToDestination"] = is_completed
    df["FlightOutcome"] = np.select([is_cancelled == 1, is_diverted == 1, is_completed == 1], ["Cancelled", "Diverted", "Completed-to-Destination"], default="Unknown")
    df["FlightOutcomeSort"] = np.select([is_completed == 1, is_cancelled == 1, is_diverted == 1], [1, 2, 3], default=4).astype(np.int32)

    is_dep_otp_elig = ((is_cancelled == 0) & df["DepDel15"].notna()).astype(np.int32)
    is_arr_otp_elig = ((is_cancelled == 0) & (is_diverted == 0) & df["ArrDel15"].notna()).astype(np.int32)
    df["IsDepOTPEligible"] = is_dep_otp_elig
    df["IsArrOTPEligible"] = is_arr_otp_elig
    df["IsEligibleForOTP"] = is_arr_otp_elig
    df["IsDepDelay15"] = ((is_dep_otp_elig == 1) & (df["DepDel15"] == 1)).astype(np.int32)
    df["IsArrDelay15"] = ((is_arr_otp_elig == 1) & (df["ArrDel15"] == 1)).astype(np.int32)

    arr_del = df["ArrDelay"]
    arr_valid = (is_arr_otp_elig == 1) & arr_del.notna()
    df["ArrDelayBand"] = np.select(
        [~arr_valid, arr_del < 0, arr_del < 15, arr_del <= 45, arr_del <= 120],
        ["N/A (Cancelled/Diverted)", "Early (<0m)", "On-time (0-14m)", "Delayed 15-45m", "Delayed 46-120m"],
        default="Severe (>120m)",
    )
    df["ArrDelayBandSort"] = np.select([~arr_valid, arr_del < 0, arr_del < 15, arr_del <= 45, arr_del <= 120], [6, 1, 2, 3, 4], default=5).astype(np.int32)

    dep_del = df["DepDelay"]
    dep_valid = (is_dep_otp_elig == 1) & dep_del.notna()
    df["DepDelayBand"] = np.select(
        [~dep_valid, dep_del < 0, dep_del < 15, dep_del <= 45, dep_del <= 120],
        ["N/A (Cancelled)", "Early (<0m)", "On-time (0-14m)", "Delayed 15-45m", "Delayed 46-120m"],
        default="Severe (>120m)",
    )
    df["DepDelayBandSort"] = np.select([~dep_valid, dep_del < 0, dep_del < 15, dep_del <= 45, dep_del <= 120], [6, 1, 2, 3, 4], default=5).astype(np.int32)

    df["IsSevereDelay"] = (arr_valid & (arr_del > 60)).astype(np.int32)
    df["IsExtremeDelay"] = (arr_valid & (arr_del > 120)).astype(np.int32)

    df.loc[df["TaxiOut"] < 0, "TaxiOut"] = np.nan
    df.loc[df["TaxiIn"] < 0, "TaxiIn"] = np.nan
    df.loc[df["AirTime"] <= 0, "AirTime"] = np.nan
    df["GroundTime"] = np.where(df["TaxiOut"].notna() & df["TaxiIn"].notna(), df["TaxiOut"] + df["TaxiIn"], np.nan)
    df["BlockTimeVariance"] = np.where(df["ActualElapsedTime"].notna() & df["CRSElapsedTime"].notna(), df["ActualElapsedTime"] - df["CRSElapsedTime"], np.nan)
    df["AirSpeedMph"] = np.where((df["AirTime"] > 0) & (df["Distance"] > 0), df["Distance"] / (df["AirTime"] / 60.0), np.nan)

    cause_cols = ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]
    any_cause_present = df[cause_cols].notna().any(axis=1)
    df["DelayCauseTotal"] = np.where(any_cause_present, df[cause_cols].fillna(0).sum(axis=1), np.nan)

    canc_code = df["CancellationCode"].fillna("").astype(str).str.strip()
    df["CancellationReasonLabel"] = np.select(
        [is_cancelled == 0, canc_code == "A", canc_code == "B", canc_code == "C", canc_code == "D"],
        [None, "A - Carrier", "B - Weather", "C - National Air System (NAS)", "D - Security"],
        default="Unknown Reason",
    )

    dim_date = build_dim_date_from_series(fdate)

    airline_counts = df.groupby("Reporting_Airline", as_index=False).size().rename(columns={"size": "ScheduledFlights"}).sort_values("Reporting_Airline").reset_index(drop=True)
    airline_counts["AirlineKey"] = np.arange(1, len(airline_counts) + 1, dtype=np.int32)
    airline_counts["AirlineName"] = airline_counts["Reporting_Airline"].map(lambda c: AIRLINE_NAMES.get(c, f"Airline {c}"))
    airline_counts["AirlineLabel"] = airline_counts["Reporting_Airline"] + " - " + airline_counts["AirlineName"]
    dim_airline = airline_counts[["AirlineKey", "Reporting_Airline", "AirlineName", "AirlineLabel", "ScheduledFlights"]]
    df["AirlineKey"] = df["Reporting_Airline"].map(dict(zip(dim_airline["Reporting_Airline"], dim_airline["AirlineKey"]))).astype(np.int32)

    orig_agg = df.groupby("Origin", as_index=False).agg(CityName=("OriginCityName", "first"), State=("OriginState", "first"), RoleFlights=("FlightKey", "count")).rename(columns={"Origin": "AirportCode"})
    dim_origin = compute_pareto_abc(orig_agg, "RoleFlights", "AirportGroup")
    dim_origin["AirportKey"] = np.arange(1, len(dim_origin) + 1, dtype=np.int32)
    dim_origin["AirportLabel"] = dim_origin["AirportCode"] + " (" + dim_origin["CityName"].astype(str) + ")"

    dest_agg = df.groupby("Dest", as_index=False).agg(CityName=("DestCityName", "first"), State=("DestState", "first"), RoleFlights=("FlightKey", "count")).rename(columns={"Dest": "AirportCode"})
    dim_dest = compute_pareto_abc(dest_agg, "RoleFlights", "AirportGroup")
    dim_dest["AirportKey"] = np.arange(1, len(dim_dest) + 1, dtype=np.int32)
    dim_dest["AirportLabel"] = dim_dest["AirportCode"] + " (" + dim_dest["CityName"].astype(str) + ")"

    df["OriginAirportKey"] = df["Origin"].map(dict(zip(dim_origin["AirportCode"], dim_origin["AirportKey"]))).astype(np.int32)
    df["DestinationAirportKey"] = df["Dest"].map(dict(zip(dim_dest["AirportCode"], dim_dest["AirportKey"]))).astype(np.int32)

    route_agg = df.groupby("RouteKey", as_index=False).agg(
        RouteLabel=("Route", "first"), Origin=("Origin", "first"), Dest=("Dest", "first"),
        OriginState=("OriginState", "first"), DestState=("DestState", "first"),
        AvgDistance=("Distance", "mean"), DistanceBand=("DistanceBand", "first"),
        DistanceBandSort=("DistanceBandSort", "first"), RouteFlights=("FlightKey", "count"),
    )
    dim_route = compute_pareto_abc(route_agg, "RouteFlights", "RouteGroup")

    hours = np.arange(0, 24, dtype=np.int32)
    dim_timeblock = pd.DataFrame({
        "DepHour": hours,
        "HourLabel": [f"{h:02d}:00" for h in hours],
        "DepTimeBlock": ["Early Morning" if h <= 5 else ("Morning" if h <= 11 else ("Afternoon" if h <= 17 else "Evening/Night")) for h in hours],
        "DepTimeBlockSort": [1 if h <= 5 else (2 if h <= 11 else (3 if h <= 17 else 4)) for h in hours],
    })

    cause_mapping = [("CarrierDelay", "Carrier", 1), ("WeatherDelay", "Weather", 2), ("NASDelay", "NAS", 3), ("SecurityDelay", "Security", 4), ("LateAircraftDelay", "Late Aircraft", 5)]
    cause_frames = []
    fk_cols = ["FlightKey", "DateKey", "AirlineKey", "OriginAirportKey", "DestinationAirportKey", "RouteKey", "DepHour", "ArrDelayBand"]
    for col_name, label, c_sort in cause_mapping:
        sub = df.loc[df[col_name].notna() & (df[col_name] > 0), fk_cols + [col_name]].copy()
        sub["CauseName"] = label
        sub["CauseSort"] = np.int32(c_sort)
        sub = sub.rename(columns={col_name: "CauseMinutes"})
        cause_frames.append(sub)
    fact_delay_cause = pd.concat(cause_frames, ignore_index=True)

    fact_cols = [
        "FlightKey", "DateKey", "AirlineKey", "OriginAirportKey", "DestinationAirportKey", "RouteKey",
        "DepHour", "ArrHour", "Flight_Number_Reporting_Airline", "CRSDepTime", "CRSDepTimeFormatted",
        "DepTime", "DepDelay", "DepDelayMinutes", "DepDel15", "TaxiOut", "WheelsOff", "WheelsOn", "TaxiIn",
        "CRSArrTime", "CRSArrTimeFormatted", "ArrTime", "ArrDelay", "ArrDelayMinutes", "ArrDel15",
        "Cancelled", "CancellationCode", "CancellationReasonLabel", "Diverted", "CRSElapsedTime",
        "ActualElapsedTime", "AirTime", "Distance", "CarrierDelay", "WeatherDelay", "NASDelay",
        "SecurityDelay", "LateAircraftDelay", "DelayCauseTotal", "GroundTime", "BlockTimeVariance",
        "AirSpeedMph", "DepTimeBlock", "DepTimeBlockSort", "DistanceBand", "DistanceBandSort",
        "DepDelayBand", "DepDelayBandSort", "ArrDelayBand", "ArrDelayBandSort", "FlightOutcome",
        "FlightOutcomeSort", "IsCancelled", "IsDiverted", "IsOperated", "IsCompletedToDestination",
        "IsDepOTPEligible", "IsArrOTPEligible", "IsEligibleForOTP", "IsDepDelay15", "IsArrDelay15",
        "IsSevereDelay", "IsExtremeDelay",
    ]
    fact_flight = df[fact_cols]

    tables_to_export = {
        "Fact_Flight": fact_flight,
        "Fact_DelayCause": fact_delay_cause,
        "Dim_Date": dim_date,
        "Dim_Airline": dim_airline,
        "Dim_OriginAirport": dim_origin,
        "Dim_DestinationAirport": dim_dest,
        "Dim_Route": dim_route,
        "Dim_TimeBlock": dim_timeblock,
    }
    return _export_warehouse_tables(tables_to_export, warehouse_dir, csv_out_dir, reports_dir, n_source, n_dups, n_clean, t0)


def _build_universal_star_schema(
    df: pd.DataFrame,
    blueprint: Dict[str, Any],
    warehouse_dir: Path,
    csv_out_dir: Path,
    reports_dir: Path,
    t0: float,
) -> Dict[str, Any]:
    """Universal Star Schema builder for ANY CSV file with Requirement-driven ETL cleaning."""
    n_source = len(df)
    rules = blueprint.get("cleaning_rules") or []
    if not rules:
        rules = [{"column": "ALL", "action": "drop_duplicates", "condition": "ALL", "description": "Loại bản ghi trùng hoàn toàn"}]

    df, cleaning_report = apply_cleaning_rules(df, rules)
    n_clean = len(df)
    n_dups = sum(s.get("rows_dropped", 0) for s in cleaning_report.get("steps", []) if s.get("action") == "drop_duplicates")
    print(
        f"[Phase 3 ETL Clean] Applied {cleaning_report['rules_count']} rules from Requirement.md: "
        f"{n_source:,} -> {n_clean:,} rows (dropped {cleaning_report['total_rows_dropped']:,}, fixed {cleaning_report['total_cells_fixed']:,} cells)"
    )

    df["RecordKey"] = np.arange(1, n_clean + 1, dtype=np.int64)
    date_col = blueprint.get("project", {}).get("primary_date_col")
    tables_to_export: Dict[str, pd.DataFrame] = {}

    date_fmts = extract_date_format_map(rules)
    date_str_fmt = date_fmts.get("_primary_strftime", "%Y-%m-%d")
    if date_col and date_col in df.columns:
        fdate = pd.to_datetime(df[date_col], errors="coerce")
        df["DateKey"] = (fdate.dt.year.fillna(2025) * 10000 + fdate.dt.month.fillna(1) * 100 + fdate.dt.day.fillna(1)).astype(np.int32)
        tables_to_export["Dim_Date"] = build_dim_date_from_series(fdate, date_str_fmt=date_str_fmt)

    # Build Dimension tables with Pareto ABC
    dimensions_cfg = blueprint.get("universal_schema", {}).get("dimensions", [])
    for dcfg in dimensions_cfg:
        src_col = dcfg["source_column"]
        t_name = dcfg["table_name"]
        k_col = dcfg["key_column"]
        if src_col not in df.columns:
            continue
        df[src_col] = df[src_col].fillna("Unknown").astype(str).str.strip()
        agg = df.groupby(src_col, as_index=False).agg(RecordCount=("RecordKey", "count"))
        dim_df = compute_pareto_abc(agg, "RecordCount", "ParetoGroup")
        dim_df[k_col] = np.arange(1, len(dim_df) + 1, dtype=np.int32)
        cols_order = [k_col, src_col, "RecordCount", "VolumeSharePct", "CumulativeSharePct", "ParetoGroup", "ParetoGroupCode"]
        dim_df = dim_df[cols_order]
        tables_to_export[t_name] = dim_df
        df[k_col] = df[src_col].map(dict(zip(dim_df[src_col], dim_df[k_col]))).astype(np.int32)

    fact_table_name = blueprint.get("project", {}).get("fact_table_name", "Fact_Main")
    tables_to_export[fact_table_name] = df
    return _export_warehouse_tables(
        tables_to_export, warehouse_dir, csv_out_dir, reports_dir, n_source, n_dups, n_clean, t0,
        cleaning_report=cleaning_report,
    )


def _export_warehouse_tables(
    tables_to_export: Dict[str, pd.DataFrame],
    warehouse_dir: Path,
    csv_out_dir: Path,
    reports_dir: Path,
    n_source: int,
    n_dups: int,
    n_clean: int,
    t0: float,
    cleaning_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    export_stats = {}
    for tname, tdf in tables_to_export.items():
        p_path = warehouse_dir / f"{tname}.parquet"
        c_path = csv_out_dir / f"{tname}.csv"
        print(f"[Phase 4] Exporting {tname} ({len(tdf):,} rows) -> Parquet & CSV...")
        pq.write_table(pa.Table.from_pandas(tdf, preserve_index=False), str(p_path), compression="snappy")
        tdf.to_csv(c_path, index=False, encoding="utf-8")
        export_stats[tname] = {
            "rows": len(tdf),
            "columns": len(tdf.columns),
            "parquet_path": str(p_path),
            "parquet_size_mb": round(p_path.stat().st_size / (1024 * 1024), 2),
            "csv_path": str(c_path),
            "csv_size_mb": round(c_path.stat().st_size / (1024 * 1024), 2),
        }

    etl_log = {
        "status": "SUCCESS",
        "source_rows": n_source,
        "dropped_duplicate_rows": n_dups,
        "clean_fact_rows": n_clean,
        "cleaning_report": cleaning_report or {
            "source_rows": n_source,
            "clean_rows": n_clean,
            "total_rows_dropped": n_source - n_clean,
            "total_cells_fixed": 0,
            "rules_count": 1,
            "steps": [{"step": 1, "column": "ALL", "action": "drop_duplicates", "condition": "ALL", "rows_dropped": n_dups, "cells_fixed": 0, "status": "APPLIED", "detail": f"Loại {n_dups:,} dòng trùng lặp"}],
        },
        "tables": export_stats,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    with open(reports_dir / "etl_warehouse_log.json", "w", encoding="utf-8") as f:
        json.dump(etl_log, f, ensure_ascii=False, indent=2)
    print(f"[Phase 3 & 4] Star Schema Data Warehouse built in {etl_log['elapsed_seconds']}s.")
    return etl_log


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    build_data_warehouse(str(root))
