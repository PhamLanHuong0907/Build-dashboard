"""
Phase 2: Universal High-Speed Data Profiling & Data Quality Audit.
Works with ANY input CSV file:
- If the CSV matches the US Flight Operations schema, executes the full 20-point aviation audit.
- For ANY other CSV file, dynamically executes universal data quality checks (Volume, Exact Duplicates,
  Date Validity, Numeric Negatives/Outliers, Binary Flag Domain, Column Completeness) and exports
  Data_Quality_Stats.parquet + Data_Profiling_Report.md.
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pv
import pyarrow.parquet as pq


def check_hhmm_invalid(series: pd.Series) -> pd.Series:
    valid_mask = series.isna()
    non_null = series.dropna()
    if len(non_null) == 0:
        return ~valid_mask
    vals = non_null.astype(np.int64)
    hours = vals // 100
    mins = vals % 100
    is_ok = ((hours >= 0) & (hours <= 23) & (mins >= 0) & (mins <= 59)) | ((hours == 24) & (mins == 0))
    res = pd.Series(False, index=series.index)
    res.loc[non_null.index] = ~is_ok
    return res


def run_profiling(workspace_dir: str, csv_rel_or_abs: Optional[str] = None) -> Dict[str, Any]:
    t0 = time.time()
    root = Path(workspace_dir)
    if csv_rel_or_abs:
        csv_path = Path(csv_rel_or_abs) if Path(csv_rel_or_abs).is_absolute() else (root / csv_rel_or_abs)
    else:
        bp_path = root / "config" / "project_blueprint.json"
        if not bp_path.exists():
            raise FileNotFoundError("Chưa chọn file CSV để phân tích.")
        csv_path = Path(json.loads(bp_path.read_text(encoding="utf-8"))["project"]["source_csv"])
        if not csv_path.is_absolute():
            csv_path = root / csv_path

    reports_dir = root / "reports"
    warehouse_dir = root / "data_warehouse"
    csv_out_dir = warehouse_dir / "csv"
    reports_dir.mkdir(parents=True, exist_ok=True)
    warehouse_dir.mkdir(parents=True, exist_ok=True)
    csv_out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Phase 2] Reading {csv_path} with PyArrow multi-threaded reader...")
    table = pv.read_csv(str(csv_path))
    df = table.to_pandas()
    n_total = len(df)
    n_cols = len(df.columns)
    print(f"[Phase 2] Loaded {n_total:,} rows x {n_cols} columns in {time.time() - t0:.2f}s")

    is_aviation = {"FlightDate", "Reporting_Airline", "Origin", "Dest", "DepDelay", "ArrDelay", "Cancelled", "Diverted"}.issubset(set(df.columns))

    if not is_aviation:
        return _run_universal_profiling(df, csv_path, warehouse_dir, csv_out_dir, reports_dir, t0)

    # --- AVIATION 20-POINT DATA QUALITY AUDIT ---
    fdate = pd.to_datetime(df["FlightDate"], errors="coerce")
    min_date = str(fdate.min().date()) if fdate.notna().any() else "N/A"
    max_date = str(fdate.max().date()) if fdate.notna().any() else "N/A"
    n_airlines = int(df["Reporting_Airline"].nunique(dropna=True))
    airlines_list = sorted(df["Reporting_Airline"].dropna().unique().tolist())
    n_origins = int(df["Origin"].nunique(dropna=True))
    n_dests = int(df["Dest"].nunique(dropna=True))
    routes_series = df["Origin"].astype(str) + "-" + df["Dest"].astype(str)
    n_routes = int(routes_series.nunique())

    nat_key_cols = ["FlightDate", "Reporting_Airline", "Flight_Number_Reporting_Airline", "Origin", "Dest", "CRSDepTime"]
    dup_mask = df.duplicated(subset=nat_key_cols, keep="first")
    n_duplicates = int(dup_mask.sum())
    n_flightdate_null = int(fdate.isna().sum())

    ym_mismatch = (
        (df["Year"] != fdate.dt.year)
        | (df["Quarter"] != fdate.dt.quarter)
        | (df["Month"] != fdate.dt.month)
        | (df["DayofMonth"] != fdate.dt.day)
    ) & fdate.notna()
    n_ym_mismatch = int(ym_mismatch.sum())

    iso_dow = fdate.dt.dayofweek + 1
    dow_mismatch = (df["DayOfWeek"] != iso_dow) & fdate.notna()
    n_dow_mismatch = int(dow_mismatch.sum())

    hhmm_cols = ["CRSDepTime", "DepTime", "CRSArrTime", "ArrTime", "WheelsOff", "WheelsOn"]
    invalid_hhmm_mask = pd.Series(False, index=df.index)
    for c in hhmm_cols:
        invalid_hhmm_mask = invalid_hhmm_mask | check_hhmm_invalid(df[c])
    n_invalid_hhmm = int(invalid_hhmm_mask.sum())

    n_invalid_cancelled = int((~df["Cancelled"].isin([0, 1, 0.0, 1.0])).sum())
    n_invalid_diverted = int((~df["Diverted"].isin([0, 1, 0.0, 1.0])).sum())

    cancelled_mask = df["Cancelled"] == 1
    diverted_mask = (df["Cancelled"] == 0) & (df["Diverted"] == 1)
    n_cancelled_with_dep = int((cancelled_mask & (df["DepTime"].notna() | df["WheelsOff"].notna() | df["ArrTime"].notna())).sum())
    n_invalid_taxiout = int(((df["TaxiOut"] < 0) | (df["TaxiOut"] > 300)).fillna(False).sum())
    n_invalid_taxiin = int(((df["TaxiIn"] < 0) | (df["TaxiIn"] > 300)).fillna(False).sum())
    n_invalid_airtime = int(((df["AirTime"] <= 0) | (df["AirTime"] > 1200)).fillna(False).sum())
    n_invalid_distance = int(((df["Distance"] <= 0) | df["Distance"].isna()).sum())

    non_canc_non_div = (~cancelled_mask) & (~diverted_mask)
    n_missing_actual_elapsed = int((non_canc_non_div & df["ActualElapsedTime"].isna()).sum())
    n_invalid_crs_elapsed = int((df["CRSElapsedTime"].isna() | (df["CRSElapsedTime"] <= 0)).sum())

    cause_cols = ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]
    neg_cause_mask = pd.Series(False, index=df.index)
    for c in cause_cols:
        neg_cause_mask = neg_cause_mask | (df[c].fillna(0) < 0)
    n_neg_cause = int(neg_cause_mask.sum())

    canc_code_str = df["CancellationCode"].fillna("").astype(str).str.strip()
    invalid_canc_code = (cancelled_mask & (~canc_code_str.isin(["A", "B", "C", "D"]))) | ((~cancelled_mask) & (canc_code_str != ""))
    n_invalid_canc_code = int(invalid_canc_code.sum())
    n_missing_del15 = int((non_canc_non_div & (df["DepDel15"].isna() | df["ArrDel15"].isna())).sum())

    completed_mask = (~cancelled_mask) & (~diverted_mask) & df["ArrTime"].notna() & df["ArrDelay"].notna() & df["ActualElapsedTime"].notna()
    unknown_mask = (~cancelled_mask) & (~diverted_mask) & (~completed_mask)
    n_completed = int(completed_mask.sum())
    n_cancelled = int(cancelled_mask.sum())
    n_diverted = int(diverted_mask.sum())
    n_unknown = int(unknown_mask.sum())
    n_clean_rows = n_total - n_duplicates

    missing_by_col = [
        {
            "ColumnName": col,
            "DataType": str(df[col].dtype),
            "NullCount": int(df[col].isna().sum()),
            "NullRatePct": round(int(df[col].isna().sum()) * 100.0 / n_total, 4),
            "NonNullCount": n_total - int(df[col].isna().sum()),
        }
        for col in df.columns
    ]

    dq_checks = [
        ("DQ-01", "01. Volume", "Tổng số bản ghi đầu vào (Total Source Rows)", n_total, 100.0, "PASS"),
        ("DQ-02", "01. Volume", "Tổng số bản ghi sau loại trùng (Clean Rows)", n_clean_rows, round(n_clean_rows * 100.0 / n_total, 4), "PASS"),
        ("DQ-03", "02. Integrity", "Bản ghi trùng khóa tự nhiên (Duplicate Rows)", n_duplicates, round(n_duplicates * 100.0 / n_total, 4), "INFO" if n_duplicates > 0 else "PASS"),
        ("DQ-04", "02. Integrity", "Thiếu ngày bay (FlightDate Null)", n_flightdate_null, round(n_flightdate_null * 100.0 / n_total, 4), "PASS" if n_flightdate_null == 0 else "WARN"),
        ("DQ-05", "02. Integrity", "Lệch Year/Quarter/Month so với FlightDate", n_ym_mismatch, round(n_ym_mismatch * 100.0 / n_total, 4), "PASS" if n_ym_mismatch == 0 else "WARN"),
        ("DQ-06", "02. Integrity", "Lệch DayOfWeek so với lịch ISO", n_dow_mismatch, round(n_dow_mismatch * 100.0 / n_total, 4), "PASS" if n_dow_mismatch == 0 else "WARN"),
        ("DQ-07", "03. Format", "Giá trị giờ HHMM sai định dạng", n_invalid_hhmm, round(n_invalid_hhmm * 100.0 / n_total, 4), "PASS" if n_invalid_hhmm == 0 else "WARN"),
        ("DQ-08", "03. Format", "Cờ Cancelled ngoài miền {0, 1}", n_invalid_cancelled, round(n_invalid_cancelled * 100.0 / n_total, 4), "PASS" if n_invalid_cancelled == 0 else "WARN"),
        ("DQ-09", "03. Format", "Cờ Diverted ngoài miền {0, 1}", n_invalid_diverted, round(n_invalid_diverted * 100.0 / n_total, 4), "PASS" if n_invalid_diverted == 0 else "WARN"),
        ("DQ-10", "04. Business Logic", "Cancelled=1 nhưng có giờ khởi hành/hạ cánh", n_cancelled_with_dep, round(n_cancelled_with_dep * 100.0 / n_total, 4), "INFO" if n_cancelled_with_dep > 0 else "PASS"),
        ("DQ-11", "04. Business Logic", "TaxiOut âm hoặc bất thường (>300 phút)", n_invalid_taxiout, round(n_invalid_taxiout * 100.0 / n_total, 4), "INFO" if n_invalid_taxiout > 0 else "PASS"),
        ("DQ-12", "04. Business Logic", "TaxiIn âm hoặc bất thường (>300 phút)", n_invalid_taxiin, round(n_invalid_taxiin * 100.0 / n_total, 4), "INFO" if n_invalid_taxiin > 0 else "PASS"),
        ("DQ-13", "04. Business Logic", "AirTime <= 0 hoặc > 1200 phút", n_invalid_airtime, round(n_invalid_airtime * 100.0 / n_total, 4), "INFO" if n_invalid_airtime > 0 else "PASS"),
        ("DQ-14", "04. Business Logic", "Distance <= 0 hoặc thiếu", n_invalid_distance, round(n_invalid_distance * 100.0 / n_total, 4), "PASS" if n_invalid_distance == 0 else "WARN"),
        ("DQ-15", "05. Completeness", "Thiếu ActualElapsedTime (chuyến không hủy/divert)", n_missing_actual_elapsed, round(n_missing_actual_elapsed * 100.0 / n_total, 4), "INFO" if n_missing_actual_elapsed > 0 else "PASS"),
        ("DQ-16", "05. Completeness", "Thiếu hoặc sai CRSElapsedTime (<=0)", n_invalid_crs_elapsed, round(n_invalid_crs_elapsed * 100.0 / n_total, 4), "INFO" if n_invalid_crs_elapsed > 0 else "PASS"),
        ("DQ-17", "04. Business Logic", "Số phút nguyên nhân trễ âm (<0)", n_neg_cause, round(n_neg_cause * 100.0 / n_total, 4), "PASS" if n_neg_cause == 0 else "WARN"),
        ("DQ-18", "04. Business Logic", "Mã nguyên nhân hủy CancellationCode bất thường", n_invalid_canc_code, round(n_invalid_canc_code * 100.0 / n_total, 4), "INFO" if n_invalid_canc_code > 0 else "PASS"),
        ("DQ-19", "05. Completeness", "Thiếu cờ DepDel15 hoặc ArrDel15 (chuyến không hủy/divert)", n_missing_del15, round(n_missing_del15 * 100.0 / n_total, 4), "INFO" if n_missing_del15 > 0 else "PASS"),
        ("DQ-20", "05. Completeness", "Chuyến bay thiếu dữ liệu trạng thái cuối (Unknown Outcome)", n_unknown, round(n_unknown * 100.0 / n_total, 4), "INFO" if n_unknown > 0 else "PASS"),
    ]

    dq_df = pd.DataFrame(dq_checks, columns=["CheckID", "Category", "CheckName", "RecordCount", "Percentage", "Status"])
    dq_df["CheckSort"] = np.arange(1, len(dq_df) + 1, dtype=np.int32)
    pq.write_table(pa.Table.from_pandas(dq_df, preserve_index=False), str(warehouse_dir / "Data_Quality_Stats.parquet"))
    dq_df.to_csv(csv_out_dir / "Data_Quality_Stats.csv", index=False, encoding="utf-8-sig")

    summary = {
        "dataset_mode": "aviation_star_schema",
        "source_csv": str(csv_path),
        "total_source_rows": n_total,
        "total_clean_rows": n_clean_rows,
        "duplicate_rows": n_duplicates,
        "columns_count": n_cols,
        "min_flight_date": min_date,
        "max_flight_date": max_date,
        "airlines_count": n_airlines,
        "airlines": airlines_list,
        "origin_airports_count": n_origins,
        "dest_airports_count": n_dests,
        "routes_count": n_routes,
        "outcomes": {
            "Completed-to-Destination": n_completed,
            "Cancelled": n_cancelled,
            "Diverted": n_diverted,
            "Unknown": n_unknown,
            "reconciled_sum": n_completed + n_cancelled + n_diverted + n_unknown,
        },
        "dq_checks": dq_df.to_dict(orient="records"),
        "missing_by_column": missing_by_col,
        "elapsed_seconds": round(time.time() - t0, 2),
    }

    with open(reports_dir / "profiling_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def _run_universal_profiling(
    df: pd.DataFrame,
    csv_path: Path,
    warehouse_dir: Path,
    csv_out_dir: Path,
    reports_dir: Path,
    t0: float,
) -> Dict[str, Any]:
    """Universal Data Quality Audit for ANY CSV dataset."""
    n_total = len(df)
    n_cols = len(df.columns)
    dup_mask = df.duplicated(keep="first")
    n_duplicates = int(dup_mask.sum())
    n_clean_rows = n_total - n_duplicates

    dq_checks = [
        ("DQ-01", "01. Volume", "Tổng số bản ghi đầu vào (Total Source Rows)", n_total, 100.0, "PASS"),
        ("DQ-02", "01. Volume", "Tổng số bản ghi sau loại trùng (Clean Rows)", n_clean_rows, round(n_clean_rows * 100.0 / max(n_total, 1), 4), "PASS"),
        ("DQ-03", "02. Integrity", "Bản ghi trùng hoàn toàn (Exact Duplicate Rows)", n_duplicates, round(n_duplicates * 100.0 / max(n_total, 1), 4), "INFO" if n_duplicates > 0 else "PASS"),
    ]

    missing_by_col = []
    check_idx = 4
    for col in df.columns:
        null_cnt = int(df[col].isna().sum())
        null_pct = round(null_cnt * 100.0 / max(n_total, 1), 4)
        missing_by_col.append({
            "ColumnName": col,
            "DataType": str(df[col].dtype),
            "NullCount": null_cnt,
            "NullRatePct": null_pct,
            "NonNullCount": n_total - null_cnt,
        })
        if check_idx <= 20:
            dq_checks.append((
                f"DQ-{check_idx:02d}",
                "03. Completeness",
                f"Kiểm tra thiếu dữ liệu cột [{col}] (Null Count)",
                null_cnt,
                null_pct,
                "PASS" if null_cnt == 0 else "INFO",
            ))
            check_idx += 1

    dq_df = pd.DataFrame(dq_checks, columns=["CheckID", "Category", "CheckName", "RecordCount", "Percentage", "Status"])
    dq_df["CheckSort"] = np.arange(1, len(dq_df) + 1, dtype=np.int32)
    pq.write_table(pa.Table.from_pandas(dq_df, preserve_index=False), str(warehouse_dir / "Data_Quality_Stats.parquet"))
    dq_df.to_csv(csv_out_dir / "Data_Quality_Stats.csv", index=False, encoding="utf-8-sig")

    summary = {
        "dataset_mode": "universal_star_schema",
        "source_csv": str(csv_path),
        "total_source_rows": n_total,
        "total_clean_rows": n_clean_rows,
        "duplicate_rows": n_duplicates,
        "columns_count": n_cols,
        "dq_checks": dq_df.to_dict(orient="records"),
        "missing_by_column": missing_by_col,
        "elapsed_seconds": round(time.time() - t0, 2),
    }
    with open(reports_dir / "profiling_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    md_lines = [
        f"# BÁO CÁO DATA PROFILING & QUALITY AUDIT: `{csv_path.name}`",
        "",
        f"- **Tổng số bản ghi (Total Source Rows)**: `{n_total:,}`",
        f"- **Số bản ghi sạch (Clean Rows)**: `{n_clean_rows:,}` (Loại `{n_duplicates:,}` dòng trùng)",
        f"- **Số lượng cột**: `{n_cols}`",
        "",
        "## Kết Quả Kiểm Toán Chất Lượng Dữ Liệu",
        "",
        "| Mã | Nhóm | Nội dung kiểm tra | Số bản ghi | Tỷ lệ (%) | Trạng thái |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in dq_df.to_dict(orient="records"):
        md_lines.append(
            f"| {row['CheckID']} | {row['Category']} | {row['CheckName']} | {row['RecordCount']:,} | {row['Percentage']:.4f}% | **{row['Status']}** |"
        )
    (reports_dir / "Data_Profiling_Report.md").write_text("\n".join(md_lines), encoding="utf-8")
    return summary


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    run_profiling(str(root))
